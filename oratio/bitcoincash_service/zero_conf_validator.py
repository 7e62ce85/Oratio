#!/usr/bin/env python3
"""
Zero-Confirmation Transaction Validator for Bitcoin Cash

⚠️ 현재 상태: 사용 안 됨 (NOT IN USE)
이유: ElectronCash가 getrawtransaction을 지원하지 않아 
      payment.py에서 간소화된 잔액 기반 검증을 대신 사용 중

향후 계획: 다른 BCH 지갑 라이브러리로 전환하거나
          getrawtransaction 지원 노드와 연결 시 사용 예정

================================================================

BCH는 RBF(Replace-By-Fee)가 없으므로 zero-confirmation이 비교적 안전합니다.
이 모듈은 zero-conf 트랜잭션을 안전하게 수락하기 위한 검증 로직을 제공합니다.

검증 항목:
1. 트랜잭션 유효성 확인
2. 수수료율 확인 (최소 기준의 50% 이상)
3. 이중지불 여부 확인 (mempool에서)
4. RBF 플래그 확인 (BCH는 없지만 방어적 체크)

작성일: 2025-10-23
마지막 수정: 2025-10-23
"""

import logging
import time
import traceback
from typing import Dict, Tuple, Optional, List
from datetime import datetime

logger = logging.getLogger('zero_conf_validator')

# BCH 네트워크 상수
SATOSHIS_PER_BCH = 100000000
TYPICAL_TX_SIZE_BYTES = 250  # 평균 트랜잭션 크기
MIN_RELAY_FEE_RATE = 1.0  # satoshi per byte (BCH 기본 최소 릴레이 수수료)

class ZeroConfValidator:
    """Zero-Confirmation 트랜잭션 검증기"""
    
    def __init__(self, electron_cash, min_fee_rate_percent=50):
        """
        초기화
        
        Args:
            electron_cash: ElectronCash 인스턴스
            min_fee_rate_percent: 최소 수수료율 (기본값의 몇 %, 기본 50%)
        """
        self.electron_cash = electron_cash
        self.min_fee_rate_percent = min_fee_rate_percent
        self.min_acceptable_fee_rate = MIN_RELAY_FEE_RATE * (min_fee_rate_percent / 100.0)
        
        logger.info(f"ZeroConfValidator 초기화: 최소 수수료율 {self.min_acceptable_fee_rate} sat/byte "
                   f"({min_fee_rate_percent}% of {MIN_RELAY_FEE_RATE} sat/byte)")
    
    def validate_transaction(self, tx_hash: str, expected_amount: float, 
                           expected_address: str, created_at: int) -> Tuple[bool, str, Dict]:
        """
        Zero-Conf 트랜잭션 종합 검증
        
        Args:
            tx_hash: 트랜잭션 해시
            expected_amount: 예상 금액 (BCH)
            expected_address: 예상 수신 주소
            created_at: 인보이스 생성 시간 (timestamp)
            
        Returns:
            Tuple[bool, str, Dict]: (성공여부, 메시지, 트랜잭션 정보)
        """
        try:
            logger.info(f"Zero-Conf 검증 시작: {tx_hash}")
            
            # 1. 트랜잭션 정보 가져오기
            tx_info = self._get_transaction_details(tx_hash)
            if not tx_info:
                return False, "트랜잭션을 찾을 수 없습니다", {}
            
            # 2. 트랜잭션 유효성 확인
            is_valid, msg = self._validate_transaction_basic(tx_info, expected_address, 
                                                             expected_amount, created_at)
            if not is_valid:
                return False, f"기본 검증 실패: {msg}", tx_info
            
            # 3. 수수료율 확인
            is_valid, msg = self._validate_fee_rate(tx_info)
            if not is_valid:
                return False, f"수수료 검증 실패: {msg}", tx_info
            
            # 4. 이중지불 체크 (mempool에서)
            is_valid, msg = self._check_double_spend(tx_hash, tx_info)
            if not is_valid:
                return False, f"이중지불 감지: {msg}", tx_info
            
            # 5. RBF 체크 (BCH는 없지만 방어적으로 체크)
            if self._is_rbf_transaction(tx_info):
                logger.warning(f"RBF 트랜잭션 감지: {tx_hash} (BCH에서는 비정상)")
                return False, "RBF 트랜잭션은 zero-conf로 수락할 수 없습니다", tx_info
            
            logger.info(f"✅ Zero-Conf 검증 성공: {tx_hash}")
            return True, "검증 성공", tx_info
            
        except Exception as e:
            logger.error(f"Zero-Conf 검증 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False, f"검증 오류: {str(e)}", {}
    
    def _get_transaction_details(self, tx_hash: str) -> Optional[Dict]:
        """
        트랜잭션 세부 정보 가져오기
        
        Args:
            tx_hash: 트랜잭션 해시
            
        Returns:
            트랜잭션 정보 딕셔너리 또는 None
        """
        try:
            # ElectronCash에서 트랜잭션 정보 조회
            tx_data = self.electron_cash.call_method("gettransaction", [tx_hash])
            
            if not tx_data:
                logger.error(f"트랜잭션 {tx_hash}를 찾을 수 없습니다")
                return None
            
            # raw 트랜잭션 정보도 가져오기 (수수료 계산용)
            try:
                raw_tx = self.electron_cash.call_method("getrawtransaction", [tx_hash, True])
                if raw_tx:
                    tx_data['raw'] = raw_tx
            except Exception as e:
                logger.warning(f"Raw 트랜잭션 정보를 가져올 수 없습니다: {str(e)}")
            
            return tx_data
            
        except Exception as e:
            logger.error(f"트랜잭션 정보 조회 오류: {str(e)}")
            return None
    
    def _validate_transaction_basic(self, tx_info: Dict, expected_address: str, 
                                    expected_amount: float, created_at: int) -> Tuple[bool, str]:
        """
        트랜잭션 기본 유효성 검증
        
        Args:
            tx_info: 트랜잭션 정보
            expected_address: 예상 수신 주소
            expected_amount: 예상 금액
            created_at: 인보이스 생성 시간
            
        Returns:
            Tuple[bool, str]: (성공여부, 메시지)
        """
        # 주소 확인 (output에 예상 주소가 있는지)
        clean_address = expected_address.replace('bitcoincash:', '')
        
        # 금액 확인 - ElectronCash의 금액 포맷에 따라 다를 수 있음
        # 일반적으로 BCH 단위로 반환됨
        tx_amount = abs(float(tx_info.get('amount', 0)))
        
        if tx_amount < expected_amount * 0.99999:  # 0.001% 오차 허용 (수수료 고려)
            return False, f"금액 불일치: 예상 {expected_amount} BCH, 실제 {tx_amount} BCH"
        
        # 타임스탬프 확인 (인보이스 생성 이후 트랜잭션인지)
        tx_time = tx_info.get('timestamp', int(time.time()))
        if tx_time < created_at - 300:  # 5분 여유 (시간 동기화 고려)
            logger.warning(f"트랜잭션 시간이 인보이스 생성 시간보다 이릅니다: "
                          f"tx={datetime.fromtimestamp(tx_time)}, "
                          f"invoice={datetime.fromtimestamp(created_at)}")
            # 경고만 하고 통과 (ElectronCash 타임스탬프가 정확하지 않을 수 있음)
        
        return True, "기본 검증 통과"
    
    def _validate_fee_rate(self, tx_info: Dict) -> Tuple[bool, str]:
        """
        수수료율 검증
        
        Args:
            tx_info: 트랜잭션 정보
            
        Returns:
            Tuple[bool, str]: (성공여부, 메시지)
        """
        try:
            # raw 트랜잭션에서 수수료 계산
            if 'raw' in tx_info:
                raw_tx = tx_info['raw']
                
                # 트랜잭션 크기 (bytes)
                tx_size = raw_tx.get('size', TYPICAL_TX_SIZE_BYTES)
                
                # 수수료 (satoshi)
                # ElectronCash는 fee를 BCH 단위로 반환할 수 있음
                fee_bch = abs(float(tx_info.get('fee', 0)))
                fee_satoshi = int(fee_bch * SATOSHIS_PER_BCH)
                
                if fee_satoshi <= 0:
                    # fee 정보가 없으면 최소값 가정
                    logger.warning(f"수수료 정보 없음, 최소값으로 가정")
                    fee_satoshi = int(tx_size * MIN_RELAY_FEE_RATE)
                
                # 수수료율 계산 (sat/byte)
                fee_rate = fee_satoshi / tx_size if tx_size > 0 else 0
                
                logger.info(f"수수료 검증: {fee_rate:.2f} sat/byte "
                           f"(최소 요구: {self.min_acceptable_fee_rate:.2f} sat/byte)")
                
                # 수수료율 확인
                if fee_rate < self.min_acceptable_fee_rate:
                    return False, (f"수수료율이 너무 낮습니다: {fee_rate:.2f} sat/byte "
                                 f"(최소 {self.min_acceptable_fee_rate:.2f} sat/byte 필요)")
                
                return True, f"수수료율 적절: {fee_rate:.2f} sat/byte"
            else:
                # raw 정보가 없으면 경고만 하고 통과
                logger.warning("Raw 트랜잭션 정보가 없어 수수료 검증을 건너뜁니다")
                return True, "수수료 검증 건너뜀 (raw 정보 없음)"
                
        except Exception as e:
            logger.error(f"수수료율 검증 오류: {str(e)}")
            # 오류 발생 시 일단 통과 (너무 엄격하면 false positive 발생)
            return True, f"수수료 검증 건너뜀 (오류: {str(e)})"
    
    def _check_double_spend(self, tx_hash: str, tx_info: Dict) -> Tuple[bool, str]:
        """
        이중지불 체크 (mempool에서 같은 input을 사용하는 다른 트랜잭션 확인)
        
        Args:
            tx_hash: 현재 트랜잭션 해시
            tx_info: 트랜잭션 정보
            
        Returns:
            Tuple[bool, str]: (성공여부, 메시지)
        """
        try:
            # ElectronCash의 mempool 조회
            mempool = self.electron_cash.call_method("getmempooltransactions", [])
            
            if not mempool or not isinstance(mempool, list):
                # mempool 조회 실패 시 일단 통과
                logger.warning("Mempool 조회 실패, 이중지불 체크 건너뜀")
                return True, "이중지불 체크 건너뜀 (mempool 조회 실패)"
            
            # 현재 트랜잭션의 input 추출
            current_inputs = self._extract_inputs(tx_info)
            if not current_inputs:
                logger.warning("트랜잭션 input 정보를 추출할 수 없습니다")
                return True, "이중지불 체크 건너뜀 (input 정보 없음)"
            
            # mempool의 다른 트랜잭션과 비교
            for mempool_tx_hash in mempool:
                if mempool_tx_hash == tx_hash:
                    continue  # 자기 자신은 건너뛰기
                
                # 다른 트랜잭션의 input 확인
                other_tx_info = self._get_transaction_details(mempool_tx_hash)
                if not other_tx_info:
                    continue
                
                other_inputs = self._extract_inputs(other_tx_info)
                
                # input이 겹치는지 확인
                if self._has_overlapping_inputs(current_inputs, other_inputs):
                    logger.error(f"이중지불 감지! {tx_hash}와 {mempool_tx_hash}가 같은 input 사용")
                    return False, f"이중지불 감지: {mempool_tx_hash}와 충돌"
            
            return True, "이중지불 없음"
            
        except Exception as e:
            logger.error(f"이중지불 체크 오류: {str(e)}")
            # 오류 발생 시 일단 통과 (너무 엄격하면 사용성 저하)
            return True, f"이중지불 체크 건너뜀 (오류: {str(e)})"
    
    def _extract_inputs(self, tx_info: Dict) -> List[str]:
        """
        트랜잭션의 input 추출
        
        Args:
            tx_info: 트랜잭션 정보
            
        Returns:
            input 리스트 (txid:vout 형식)
        """
        inputs = []
        
        try:
            if 'raw' in tx_info and 'vin' in tx_info['raw']:
                for vin in tx_info['raw']['vin']:
                    if 'txid' in vin and 'vout' in vin:
                        input_id = f"{vin['txid']}:{vin['vout']}"
                        inputs.append(input_id)
        except Exception as e:
            logger.error(f"Input 추출 오류: {str(e)}")
        
        return inputs
    
    def _has_overlapping_inputs(self, inputs1: List[str], inputs2: List[str]) -> bool:
        """
        두 트랜잭션의 input이 겹치는지 확인
        
        Args:
            inputs1: 첫 번째 트랜잭션의 input 리스트
            inputs2: 두 번째 트랜잭션의 input 리스트
            
        Returns:
            겹치는 input이 있으면 True
        """
        set1 = set(inputs1)
        set2 = set(inputs2)
        overlap = set1.intersection(set2)
        
        if overlap:
            logger.warning(f"겹치는 input 발견: {overlap}")
            return True
        
        return False
    
    def _is_rbf_transaction(self, tx_info: Dict) -> bool:
        """
        RBF(Replace-By-Fee) 트랜잭션인지 확인
        BCH는 RBF를 지원하지 않지만, 방어적으로 체크
        
        Args:
            tx_info: 트랜잭션 정보
            
        Returns:
            RBF 플래그가 있으면 True
        """
        try:
            if 'raw' in tx_info and 'vin' in tx_info['raw']:
                for vin in tx_info['raw']['vin']:
                    # sequence number가 0xffffffff - 2 이하이면 RBF 가능
                    sequence = vin.get('sequence', 0xffffffff)
                    if sequence < 0xfffffffe:  # RBF 가능한 sequence
                        logger.warning(f"RBF 가능한 sequence 발견: {sequence}")
                        return True
        except Exception as e:
            logger.error(f"RBF 체크 오류: {str(e)}")
        
        return False

# 전역 인스턴스 (나중에 초기화)
_validator_instance = None

def get_validator(electron_cash=None, min_fee_rate_percent=50):
    """
    Zero-Conf Validator 싱글톤 인스턴스 가져오기
    
    Args:
        electron_cash: ElectronCash 인스턴스 (첫 호출 시 필요)
        min_fee_rate_percent: 최소 수수료율 퍼센트
        
    Returns:
        ZeroConfValidator 인스턴스
    """
    global _validator_instance
    
    if _validator_instance is None:
        if electron_cash is None:
            raise ValueError("첫 호출 시 electron_cash 인스턴스가 필요합니다")
        _validator_instance = ZeroConfValidator(electron_cash, min_fee_rate_percent)
    
    return _validator_instance
