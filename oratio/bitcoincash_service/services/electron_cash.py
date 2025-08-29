import json
import time
import logging
import requests
import hashlib
import traceback
import os
from config import (
    ELECTRON_CASH_URL, ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD,
    PAYOUT_WALLET, MOCK_MODE, DIRECT_MODE, logger, EC_AVAILABLE
)
import models

class ElectronCashClient:
    def __init__(self, url=ELECTRON_CASH_URL):
        self.url = url
        self.headers = {'content-type': 'application/json'}
        self.auth = (ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD)
        self.rpc_id = 0
        self.auth_retries = 0
        self.max_retries = 3
        
    def call_method(self, method, params=None):
        if params is None:
            params = []
            
        self.rpc_id += 1
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": self.rpc_id,
        }
        
        try:
            logger.debug(f"RPC 호출: {method} {params}")
            response = requests.post(
                self.url, 
                data=json.dumps(payload), 
                headers=self.headers,
                auth=self.auth,
                timeout=10
            )
            
            # Check for authentication errors
            if response.status_code == 401 and self.auth_retries < self.max_retries:
                logger.warning(f"RPC 인증 실패 (시도 {self.auth_retries + 1}/{self.max_retries}). 자격 증명 재설정 중...")
                self.auth_retries += 1
                
                # Re-setup authentication and update credentials
                rpc_user, rpc_password = setup_electron_cash_auth()
                self.auth = (rpc_user, rpc_password)
                
                # Retry the call
                time.sleep(1)  # Small delay before retry
                return self.call_method(method, params)
                
            # Reset retry counter on success
            if response.status_code == 200:
                self.auth_retries = 0
            
            try:
                json_response = response.json()
                if "result" in json_response:
                    return json_response["result"]
                elif "error" in json_response:
                    logger.error(f"RPC 오류: {json_response['error']}")
                    return None
            except ValueError:
                logger.error(f"RPC 응답이 유효한 JSON이 아닙니다: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            if "401" in str(e) and self.auth_retries < self.max_retries:
                logger.warning(f"RPC 인증 실패 예외 (시도 {self.auth_retries + 1}/{self.max_retries}). 자격 증명 재설정 중...")
                self.auth_retries += 1
                
                # Re-setup authentication and update credentials
                rpc_user, rpc_password = setup_electron_cash_auth()
                self.auth = (rpc_user, rpc_password)
                
                # Retry the call
                time.sleep(1)  # Small delay before retry
                return self.call_method(method, params)
            
            logger.error(f"Electron Cash 호출 오류: {str(e)}")
            return None
        
    def get_new_address(self):
        """새 BCH 주소 생성"""
        # 직접 결제 모드에서는 Coinomi 주소를 사용
        if DIRECT_MODE:
            logger.info(f"직접 결제 모드: Coinomi 지갑 주소 사용 ({PAYOUT_WALLET})")
            return PAYOUT_WALLET
        
        try:
            # 새 주소를 만들기 위해 여러 방법 시도
            # 1. createnewaddress 메소드 시도 (일부 버전에서 지원)
            logger.info("ElectronCash에서 새 주소 생성 시도 (createnewaddress)...")
            result = self.call_method("createnewaddress")
            if result:
                logger.info(f"createnewaddress로 새 주소 생성 성공: {result}")
                try:
                    models.save_address(result)
                except Exception as e:
                    # 중복 주소 저장 오류는 무시
                    logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                return result
                
            # 2. getunusedaddress 메소드 시도
            logger.info("getunusedaddress 메소드 시도 중...")
            result = self.call_method("getunusedaddress")
            if result:
                logger.info(f"getunusedaddress로 새 주소 생성 성공: {result}")
                try:
                    models.save_address(result)
                except Exception as e:
                    # 중복 주소 저장 오류는 무시
                    logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                return result
                
            # 3. getnewaddress 메소드 시도 (일부 버전에서 지원)
            logger.info("getnewaddress 메소드 시도 중...")
            result = self.call_method("getnewaddress")
            if result:
                logger.info(f"getnewaddress로 새 주소 생성 성공: {result}")
                try:
                    models.save_address(result)
                except Exception as e:
                    # 중복 주소 저장 오류는 무시
                    logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                return result
            
            # 4. 마지막 시도: addrequest로 새 주소 생성
            logger.info("addrequest 메소드로 새 주소 시도 중...")
            request_label = f"Payment Request {int(time.time())}"  # 고유한 레이블 생성
            request_result = self.call_method("addrequest", [None, request_label, None, True])
            if request_result and "address" in request_result:
                address = request_result["address"]
                logger.info(f"addrequest를 통한 새 주소 생성 성공: {address}")
                try:
                    models.save_address(address)
                except Exception as e:
                    # 중복 주소 저장 오류는 무시
                    logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                return address
            
            # 5. HD 지갑에서 주소 가져오기 시도
            logger.info("기존 사용되지 않은 주소 가져오기 시도 중...")
            unused_addresses = self.call_method("getaddresshistory", ["unused"])
            if unused_addresses and isinstance(unused_addresses, list) and len(unused_addresses) > 0:
                # 마지막으로 사용된 주소 이후의 새 주소 생성
                new_index = len(unused_addresses)
                deriv_path = f"0/{new_index}"
                derived_address = self.call_method("getaddress", [deriv_path])
                if derived_address:
                    logger.info(f"파생 경로 {deriv_path}에서 새 주소 생성: {derived_address}")
                    try:
                        models.save_address(derived_address)
                    except Exception as e:
                        # 중복 주소 저장 오류는 무시
                        logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                    return derived_address
                    
            # 모든 방법 실패 시, 데이터베이스에서 가장 최근에 저장된 주소의 인덱스를 찾아서 증가
            logger.warning("모든 ElectronCash 메소드가 실패했습니다. 데이터베이스에서 대체 주소 생성 중...")
            try:
                # 데이터베이스에서 마지막 저장된 주소 확인
                last_address = models.get_last_address()
                if last_address:
                    # 인덱스를 추출하고 증가시켜 새 주소 파생
                    # 예: "bchtest:addr1" → "bchtest:addr2"
                    from direct_payment import direct_payment_handler
                    new_address = direct_payment_handler.create_derived_address(last_address)
                    logger.info(f"데이터베이스 기반 대체 주소 생성: {new_address}")
                    try:
                        models.save_address(new_address)
                    except Exception as e:
                        logger.warning(f"주소 저장 중 오류 (무시됨): {str(e)}")
                    return new_address
            except Exception as e:
                logger.error(f"대체 주소 생성 실패: {str(e)}")
                
            logger.error("ElectronCash에서 주소 생성 실패")
        except Exception as e:
            logger.error(f"주소 생성 오류: {str(e)}")
            logger.error(traceback.format_exc())
        
        # ElectronCash 실패시 직접 처리기 사용
        try:
            from direct_payment import direct_payment_handler
            direct_address = direct_payment_handler.get_address()
            logger.info(f"직접 결제 주소 사용: {direct_address}")
            return direct_address
        except ImportError:
            logger.error("직접 결제 모듈을 불러올 수 없습니다.")
            logger.warning("모든 주소 생성 방법이 실패했습니다. 임시 주소를 생성합니다.")
            
            # 가장 최후의 방법: 랜덤 주소 생성 (테스트 목적으로만 사용)
            import random, string
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            temp_address = f"bitcoincash:temp{random_suffix}"
            logger.warning(f"임시 주소 생성: {temp_address}")
            return temp_address

    def check_address_balance(self, address):
        """주소의 잔액 확인"""
        try:
            logger.info(f"[DEBUG] Balance check requested for address: {address}")
            
            # Ensure clean address format
            clean_address = address.replace('bitcoincash:', '')
            if 'bitcoincash:' not in address:
                formatted_address = f"bitcoincash:{clean_address}"
            else:
                formatted_address = address
            
            logger.info(f"[DEBUG] Formatted address for balance check: {formatted_address}")
                
            # 직접 결제 모드에서는 API를 통해 잔액 확인
            if DIRECT_MODE:
                try:
                    from direct_payment import direct_payment_handler
                    balance = direct_payment_handler.check_address_balance(address)
                    logger.info(f"[DEBUG] DIRECT_MODE balance result: {balance} BCH for address {formatted_address}")
                    return balance
                except ImportError:
                    logger.error("[DEBUG] 직접 결제 모듈을 불러올 수 없습니다.")
                    return 0.0
                
            if MOCK_MODE:
                # Mock 모드: 지불 시뮬레이션
                logger.info(f"[DEBUG] MOCK_MODE is active. Checking for pending invoices for address {formatted_address}")
                conn = models.get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, amount, created_at FROM invoices WHERE payment_address = ? AND status = 'pending'", 
                    (clean_address,)
                )
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    invoice_id, amount, created_at = result
                    # 1분 후 지불 시뮬레이션
                    if time.time() - created_at > 60:
                        logger.info(f"[DEBUG] MOCK_MODE simulating payment of {amount} BCH for invoice {invoice_id}")
                        return amount
                    else:
                        logger.info(f"[DEBUG] MOCK_MODE invoice {invoice_id} exists but not ready for payment simulation yet")
                else:
                    logger.info(f"[DEBUG] MOCK_MODE no pending invoice found for address {formatted_address}")
                    
                return 0.0
            else:
                # ElectronCash를 통한 잔액 확인
                logger.info(f"[DEBUG] Making RPC call to check balance for address {formatted_address}")
                result = self.call_method("getaddressbalance", [formatted_address])
                
                if result is not None:
                    # 원본 응답 로깅
                    logger.info(f"[DEBUG] Raw balance response for {formatted_address}: {result}")
                    
                    # ElectronCash의 응답 형식은 {"confirmed": X, "unconfirmed": Y}
                    try:
                        confirmed_value = result.get("confirmed", 0)
                        unconfirmed_value = result.get("unconfirmed", 0)
                        
                        # 문자열인 경우 직접 float로 변환
                        if isinstance(confirmed_value, str):
                            confirmed_bch = float(confirmed_value)
                        else:
                            # 정수(satoshi)인 경우 BCH로 변환
                            confirmed_bch = float(confirmed_value) / 100000000.0
                            
                        if isinstance(unconfirmed_value, str):
                            unconfirmed_bch = float(unconfirmed_value)
                        else:
                            unconfirmed_bch = float(unconfirmed_value) / 100000000.0
                        
                        logger.info(f"[DEBUG] Calculated balance for {formatted_address}: confirmed={confirmed_bch} BCH, unconfirmed={unconfirmed_bch} BCH")
                        
                        # 매우 작은 값은 버림 (1e-6 BCH 이하는 잡음으로 간주)
                        total_bch = confirmed_bch + unconfirmed_bch
                        if total_bch < 0.000001:
                            logger.warning(f"[DEBUG] Balance too small ({total_bch} BCH), treating as zero")
                            return 0.0
                        
                        # 외부 API로 확인
                        try:
                            # Blockchair API를 통한 잔액 확인 (대체 방법)
                            logger.info(f"[DEBUG] Verifying with Blockchair API for address {clean_address}")
                            api_url = f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{clean_address}"
                            api_response = requests.get(api_url, timeout=10)
                            
                            if api_response.status_code == 200:
                                api_data = api_response.json()
                                if 'data' in api_data and clean_address in api_data['data']:
                                    address_data = api_data['data'][clean_address]['address']
                                    api_balance_sats = address_data.get('balance', 0)
                                    api_balance_bch = float(api_balance_sats) / 100000000.0
                                    
                                    logger.info(f"[DEBUG] Blockchair API balance: {api_balance_bch} BCH ({api_balance_sats} satoshis)")
                                    
                                    # 만약 API 잔액이 더 크고 의미 있는 값이면 사용
                                    if api_balance_bch > total_bch and api_balance_bch >= 0.00001:
                                        logger.info(f"[DEBUG] Using Blockchair API balance: {api_balance_bch} BCH > {total_bch} BCH")
                                        return api_balance_bch
                                    elif api_balance_bch < 0.00001 and total_bch >= 0.00001:
                                        logger.warning(f"[DEBUG] API balance ({api_balance_bch}) very low but Electron Cash shows {total_bch}. This may be a false positive!")
                                else:
                                    logger.warning(f"[DEBUG] Blockchair API didn't return data for {clean_address}")
                            else:
                                logger.warning(f"[DEBUG] Blockchair API request failed with status {api_response.status_code}")
                        except Exception as e:
                            logger.warning(f"[DEBUG] External API check failed: {str(e)}")
                        
                        # 인보이스의 경우 미확인 거래도 포함하여 반환
                        logger.info(f"[DEBUG] Final balance determination for {formatted_address}: {total_bch} BCH")
                        return total_bch
                    except (ValueError, TypeError) as e:
                        logger.error(f"[DEBUG] Balance conversion error: {str(e)}")
                        # 오류 발생 시 direct_payment 모듈 사용
                        try:
                            from direct_payment import direct_payment_handler
                            balance = direct_payment_handler.check_address_balance(formatted_address)
                            logger.info(f"[DEBUG] Fallback to direct_payment balance: {balance} BCH")
                            return balance
                        except ImportError:
                            logger.error("[DEBUG] 직접 결제 모듈을 불러올 수 없습니다.")
                            return 0.0
                else:
                    logger.error(f"[DEBUG] Failed to get balance from ElectronCash for {formatted_address}")
                    # ElectronCash 실패 시 직접 처리기로 시도
                    try:
                        from direct_payment import direct_payment_handler
                        balance = direct_payment_handler.check_address_balance(formatted_address)
                        logger.info(f"[DEBUG] Fallback to direct_payment balance after ElectronCash failure: {balance} BCH")
                        return balance
                    except ImportError:
                        logger.error("[DEBUG] 직접 결제 모듈을 불러올 수 없습니다.")
                        return 0.0

        except Exception as e:
            logger.error(f"[DEBUG] Balance check exception: {str(e)}")
            logger.error(traceback.format_exc())
            # 오류 발생 시 직접 처리기로 시도
            try:
                from direct_payment import direct_payment_handler
                return direct_payment_handler.check_address_balance(address)
            except ImportError:
                logger.error("[DEBUG] 직접 결제 모듈을 불러올 수 없습니다.")
                return 0.0

    def get_transaction_confirmations(self, tx_hash):
        """트랜잭션 확인 수 확인"""
        # 직접 결제 모드에서는 API를 통해 확인
        if DIRECT_MODE:
            try:
                from direct_payment import direct_payment_handler
                return direct_payment_handler.get_transaction_confirmations(tx_hash)
            except ImportError:
                logger.error("직접 결제 모듈을 불러올 수 없습니다.")
                return 0
    
        try:
            # ElectronCash를 통한 트랜잭션 확인 수 조회
            logger.info(f"ElectronCash를 통해 트랜잭션 {tx_hash}의 확인 수 확인 중...")
            result = self.call_method("gettransaction", [tx_hash])
            
            if result is not None:
                confirmations = result.get("confirmations", 0)
                logger.info(f"트랜잭션 {tx_hash}의 확인 수: {confirmations}")
                return confirmations
            else:
                logger.error(f"ElectronCash에서 트랜잭션 {tx_hash}의 정보를 가져오지 못했습니다.")
                # ElectronCash 실패 시 직접 처리기로 시도
                try:
                    from direct_payment import direct_payment_handler
                    return direct_payment_handler.get_transaction_confirmations(tx_hash)
                except ImportError:
                    logger.error("직접 결제 모듈을 불러올 수 없습니다.")
                    return 0
                
        except Exception as e:
            logger.error(f"트랜잭션 확인 수 조회 오류: {str(e)}")
        # ElectronCash 실패시 직접 처리기 사용
        try:
            from direct_payment import direct_payment_handler
            return direct_payment_handler.get_transaction_confirmations(tx_hash)
        except ImportError:
            logger.error("직접 결제 모듈을 불러올 수 없습니다.")
            return 0

    def list_transactions(self, address=None, count=10):
        """주소 또는 지갑의 최근 트랜잭션 목록 조회"""
        if DIRECT_MODE:
            if address:
                try:
                    from direct_payment import direct_payment_handler
                    return direct_payment_handler.get_recent_transactions(address)
                except ImportError:
                    logger.error("직접 결제 모듈을 불러올 수 없습니다.")
                    return []
            return []
            
        try:
            # ElectronCash를 통한 트랜잭션 목록 조회
            # Using 'history' instead of 'listtransactions' which is not supported by Electron Cash
            logger.info(f"ElectronCash를 통해 {'주소 ' + address if address else '지갑'}의 최근 트랜잭션 조회 중...")
            
            # Call the 'history' method which is supported by Electron Cash
            result = self.call_method("history")
            
            if result is not None:
                logger.info(f"트랜잭션 이력 찾음: {len(result)} 트랜잭션")
                return result
            else:
                logger.error("ElectronCash에서 트랜잭션 이력을 가져오지 못했습니다.")
                return []
                
        except Exception as e:
            logger.error(f"트랜잭션 목록 조회 오류: {str(e)}")
            return []

    def find_transaction_for_invoice(self, invoice):
        """인보이스에 대한 트랜잭션 찾기"""
        # Ensure all required keys exist in the invoice dictionary
        required_keys = ['id', 'payment_address', 'amount', 'created_at']
        for key in required_keys:
            if key not in invoice:
                logger.error(f"인보이스에 필수 키가 없습니다: {key}")
                return None
        
        if DIRECT_MODE:
            try:
                from direct_payment import direct_payment_handler
                return direct_payment_handler.find_payment_transaction(
                    invoice["payment_address"], 
                    invoice["amount"],
                    invoice["created_at"]
                )
            except ImportError:
                logger.error("직접 결제 모듈을 불러올 수 없습니다.")
                return None
            
        try:
            # Format address properly for comparison
            formatted_address = invoice["payment_address"]
            if not formatted_address.startswith('bitcoincash:'):
                formatted_address = f"bitcoincash:{formatted_address}"
            
            # Remove bitcoincash: prefix for address comparison
            clean_address = formatted_address.replace('bitcoincash:', '')
            logger.info(f"[DEBUG] 인보이스 {invoice['id']}의 비교 주소: {clean_address}")
            
            # 1. Try to use the 'history' method provided by Electron Cash
            logger.info(f"[DEBUG] Electron Cash history 메소드를 통해 트랜잭션 검색 중... 인보이스: {invoice['id']}")
            history = self.call_method("history")
            
            if history and isinstance(history, list):
                logger.info(f"[DEBUG] 트랜잭션 이력 정보 받음: {len(history)} 항목")
                
                # Electron Cash history format is different from listtransactions
                # Log detailed transaction information for debugging
                for tx_idx, tx in enumerate(history):
                    tx_hash = tx.get('txid', tx.get('tx_hash', 'unknown'))
                    logger.info(f"[DEBUG] 트랜잭션 #{tx_idx} 분석: TXID={tx_hash}")
                    
                    # Handle both value formats (string with + and float)
                    tx_value = tx.get('value', '0')
                    if isinstance(tx_value, str):
                        tx_value = float(tx_value.replace('+', '').strip())
                    elif isinstance(tx_value, (int, float)):
                        tx_value = float(tx_value) / 100000000.0 if tx_value > 100 else float(tx_value)
                    
                    # Skip outgoing transactions
                    if tx_value <= 0:
                        logger.info(f"[DEBUG] 트랜잭션 #{tx_idx}: 금액 {tx_value}이 0보다 작거나 같아 건너뜀")
                        continue
                    
                    # Log transaction information for debugging
                    logger.info(f"[DEBUG] 트랜잭션 #{tx_idx}: 금액 {tx_value}, 인보이스 요구액: {invoice['amount']}")
                    
                    # Search for this address in inputs and outputs
                    found_address = False
                    tx_addresses = []
                    
                    # Look for our address in transaction details
                    if 'inputs' in tx:
                        for inp in tx['inputs']:
                            if 'address' in inp:
                                addr = inp['address'].replace('bitcoincash:', '')
                                tx_addresses.append(addr)
                                if addr == clean_address:
                                    found_address = True
                                    logger.info(f"[DEBUG] 주소 {clean_address}가 트랜잭션 입력에서 발견됨")
                                    
                    if 'outputs' in tx:
                        for outp in tx['outputs']:
                            if 'address' in outp:
                                addr = outp['address'].replace('bitcoincash:', '')
                                tx_addresses.append(addr)
                                if addr == clean_address:
                                    found_address = True
                                    logger.info(f"[DEBUG] 주소 {clean_address}가 트랜잭션 출력에서 발견됨")
                    
                    # Fallback to use raw transaction call to check addresses
                    if not found_address:
                        logger.info(f"[DEBUG] 기본 주소 검색에서 일치하는 항목이 없음. 원시 트랜잭션 데이터 확인 중...")
                        
                        # Try to get transaction details using raw data
                        tx_hash = tx.get('tx_hash') or tx.get('txid')
                        if tx_hash:
                            raw_tx = self.call_method("gettransaction", [tx_hash])
                            if raw_tx and 'outputs' in raw_tx:
                                for out in raw_tx.get('outputs', []):
                                    if 'address' in out:
                                        addr = out['address'].replace('bitcoincash:', '')
                                        if addr == clean_address:
                                            found_address = True
                                            logger.info(f"[DEBUG] 주소 {clean_address}가 원시 트랜잭션 출력에서 발견됨")
                    
                    # For HD wallet or other types, we may need to handle address conversion
                    # Try to check if balance is sufficient in case we can't match address exactly
                    if not found_address and abs(tx_value - invoice["amount"]) < 0.00001:
                        # If amount matches almost exactly, this is likely our transaction
                        logger.info(f"[DEBUG] 주소는 일치하지 않지만 금액이 일치합니다: {tx_value} ≈ {invoice['amount']}")
                        found_address = True
                    
                    # Try to match the exact amount with a small tolerance
                    if found_address or not tx_addresses:
                        # Check if amount matches (with small tolerance)
                        amount_matches = abs(tx_value - invoice["amount"]) < 0.00001
                        
                        # Special case: if this is exactly our expected amount
                        if amount_matches:
                            # Get transaction time
                            tx_time = tx.get('timestamp', 0)
                            if not tx_time and 'height' in tx:
                                # If we have block height but no timestamp, estimate time
                                blocks_ago = tx.get('height', 0)
                                if blocks_ago > 0:
                                    # Average block time is ~10 minutes, convert to timestamp
                                    tx_time = int(time.time() - (blocks_ago * 600))
                            
                            # Ensure transaction was created after invoice
                            if tx_time == 0 or tx_time >= invoice["created_at"]:
                                # Get confirmations
                                confirmations = 0
                                if 'confirmations' in tx:
                                    confirmations = tx['confirmations']
                                elif 'height' in tx:
                                    height = tx['height']
                                    if height > 0:
                                        confirmations = 2  # Safe default
                                
                                tx_hash = tx.get('tx_hash') or tx.get('txid', '')
                                logger.info(f"[DEBUG] 인보이스 {invoice['id']}에 대한 트랜잭션 발견: {tx_hash} (확인 수: {confirmations})")
                                
                                return {
                                    "txid": tx_hash,
                                    "amount": tx_value,
                                    "confirmations": confirmations,
                                    "time": tx_time or int(time.time())
                                }
                
                logger.info(f"[DEBUG] 인보이스 {invoice['id']}에 맞는 트랜잭션을 찾을 수 없습니다.")
            
            # Check if balance is sufficient but we couldn't find the exact transaction
            balance = self.check_address_balance(invoice["payment_address"])
            logger.info(f"[DEBUG] 주소 {invoice['payment_address']}의 잔액: {balance} BCH (필요 금액: {invoice['amount']} BCH)")
            
            # IMPORTANT FIX: Instead of automatically creating a local fake transaction ID when balance is sufficient,
            # we now require more verification through external API for greater certainty
            if balance >= invoice["amount"]:
                # Try to verify the balance using an external API before accepting it
                try:
                    # Remove bitcoincash: prefix for API
                    clean_address = invoice["payment_address"].replace('bitcoincash:', '')
                    logger.info(f"[DEBUG] 외부 API를 통해 주소 잔액 재확인 중: {clean_address}")
                    
                    # Blockchair API를 통한 잔액 확인
                    api_url = f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{clean_address}"
                    api_response = requests.get(api_url, timeout=10)
                    
                    external_confirmed = False
                    if api_response.status_code == 200:
                        api_data = api_response.json()
                        if 'data' in api_data and clean_address in api_data['data']:
                            address_data = api_data['data'][clean_address]['address']
                            api_balance_sats = address_data.get('balance', 0)
                            api_balance_bch = float(api_balance_sats) / 100000000.0
                            
                            logger.info(f"[DEBUG] Blockchair API 잔액: {api_balance_bch} BCH ({api_balance_sats} satoshis)")
                            
                            # Only confirm if the API also shows sufficient balance
                            if api_balance_bch >= invoice["amount"]:
                                logger.info(f"[DEBUG] 외부 API가 충분한 잔액을 확인함: {api_balance_bch} BCH >= {invoice['amount']} BCH")
                                external_confirmed = True
                            else:
                                logger.warning(f"[DEBUG] 외부 API에서는 충분한 잔액이 확인되지 않음: {api_balance_bch} BCH < {invoice['amount']} BCH")
                                external_confirmed = False
                        else:
                            logger.warning(f"[DEBUG] Blockchair API에서 주소 데이터를 찾을 수 없음")
                            external_confirmed = False
                    else:
                        logger.warning(f"[DEBUG] Blockchair API 응답 오류: {api_response.status_code}")
                        external_confirmed = False
                        
                    # Only proceed if external verification passed
                    if external_confirmed:
                        # Try to get latest transaction from history instead
                        if history and isinstance(history, list):
                            for tx in sorted(history, key=lambda x: x.get('timestamp', 0), reverse=True):
                                tx_hash = tx.get('tx_hash') or tx.get('txid', '')
                                if tx_hash:
                                    # Return most recent transaction with sufficient confirmations
                                    confirmations = tx.get('confirmations', 1)
                                    logger.info(f"[DEBUG] 외부 API로 확인된 충분한 잔액, 가장 최근 트랜잭션 사용: {tx_hash}, 확인 수: {confirmations}")
                                    return {
                                        "txid": tx_hash,
                                        "amount": invoice["amount"],  # Use invoice amount since we can't match exactly
                                        "confirmations": confirmations,
                                        "time": tx.get('timestamp', int(time.time()))
                                    }
                        
                        # If we still can't find a transaction but both Electron Cash and external API confirm sufficient balance
                        # we can generate a local ID as last resort - but mark it clearly as validated by multiple sources
                        unique_string = f"{invoice['id']}:{invoice['payment_address']}:{invoice['amount']}:{invoice['created_at']}"
                        hash_object = hashlib.sha256(unique_string.encode())
                        local_txid = f"verified_{hash_object.hexdigest()[:32]}"
                        
                        logger.info(f"[DEBUG] Electron Cash와 외부 API 모두 충분한 잔액을 확인함. 검증된 로컬 ID 생성: {local_txid}")
                        return {
                            "txid": local_txid,
                            "amount": invoice["amount"],
                            "confirmations": 1,  # Assume at least 1 confirmation
                            "time": int(time.time())
                        }
                    else:
                        logger.warning(f"[DEBUG] 외부 API가 충분한 잔액을 확인하지 못함. 결제 확인 불가.")
                        return None
                        
                except Exception as e:
                    logger.error(f"[DEBUG] 외부 API 호출 중 오류: {str(e)}")
                    logger.error(traceback.format_exc())
                    # Don't fall back to local ID generation if API verification fails
                    return None
            
            # Try a direct API method as a last resort
            logger.info(f"[DEBUG] Electron Cash에서 적절한 트랜잭션을 찾을 수 없고 잔액도 부족함. 대체 방법으로 확인 중...")
            try:
                from direct_payment import direct_payment_handler
                result = direct_payment_handler.find_payment_transaction(
                    invoice["payment_address"],
                    invoice["amount"],
                    invoice["created_at"]
                )
                if result:
                    logger.info(f"[DEBUG] direct_payment_handler에서 트랜잭션 찾음: {result['txid']}")
                return result
            except ImportError:
                logger.error("[DEBUG] 직접 결제 모듈을 불러올 수 없습니다.")
                return None
                
        except Exception as e:
            logger.error(f"[DEBUG] 인보이스 트랜잭션 조회 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def forward_to_payout_wallet(self):
        """수신된 자금을 출금 지갑으로 전송"""
        if not FORWARD_PAYMENTS:
            logger.info("자금 전송 기능이 비활성화되어 있습니다.")
            return
        
        try:
            # 전송 가능한 잔액 확인
            if MOCK_MODE:
                logger.info(f"Mock 모드: 출금 지갑({PAYOUT_WALLET})으로 자금 전송 시뮬레이션")
                return
            
            # 실제 잔액 확인
            balance = self.call_method("getbalance")
            if not balance or not isinstance(balance, dict):
                logger.error("잔액 확인 실패")
                return
            
            # 확인된 잔액 처리 - 문자열이면 실수로 변환 후 사토시 단위로 변환
            confirmed_balance = balance.get("confirmed", 0)
            
            # 문자열이면 실수로 변환
            if isinstance(confirmed_balance, str):
                try:
                    confirmed_bch = float(confirmed_balance)
                    # BCH → satoshis 변환 (1 BCH = 100,000,000 satoshis)
                    confirmed_sats = int(confirmed_bch * 100000000)
                except (ValueError, TypeError):
                    logger.error(f"잔액 변환 오류: {confirmed_balance}")
                    return
            else:
                # 이미 정수나 실수 형태인 경우
                confirmed_sats = int(confirmed_balance)
            
            # 잔액 로그에 상세 정보 추가
            confirmed_bch = confirmed_sats / 100000000.0
            
            logger.info(f"현재 잔액: {confirmed_bch} BCH")
            
            # 최소 출금 금액보다 많을 경우에만 전송 (BCH 단위로 비교)
            if confirmed_bch >= MIN_PAYOUT_AMOUNT:
                # 더 높은 수수료 예약 - 50%를 전송하여 수수료 문제 회피
                amount_to_send = confirmed_bch * 0.5
                
                # 1차 시도: 더 적은 금액으로 전송 시도
                logger.info(f"1차 시도: 전체 잔액의 절반 {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
                try:
                    # payto를 사용하여 트랜잭션 생성
                    result = self.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                    
                    if result:
                        # 트랜잭션 서명 및 브로드캐스트
                        signed = self.call_method("signtransaction", [result])
                        if signed:
                            broadcast = self.call_method("broadcast", [signed])
                            if broadcast:
                                logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                                logger.info(f"트랜잭션 ID: {broadcast}")
                                return
                except Exception as e:
                    logger.error(f"1차 시도 실패: {str(e)}")
                
                # 2차 시도: 더 적은 금액으로 재시도
                amount_to_send = confirmed_bch * 0.3
                logger.info(f"2차 시도: 전체 잔액의 30% {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
                try:
                    result = self.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                    
                    if result:
                        # 트랜잭션 서명 및 브로드캐스트
                        signed = self.call_method("signtransaction", [result])
                        if signed:
                            broadcast = self.call_method("broadcast", [signed])
                            if broadcast:
                                logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                                logger.info(f"트랜잭션 ID: {broadcast}")
                                return
                except Exception as e:
                    logger.error(f"2차 시도 실패: {str(e)}")
                
                # 3차 시도: 아주 적은 금액으로 전송
                amount_to_send = MIN_PAYOUT_AMOUNT  # 최소 금액만 전송
                logger.info(f"3차 시도: 최소 금액 {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
                try:
                    result = self.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                    
                    if result:
                        # 트랜잭션 서명 및 브로드캐스트
                        signed = self.call_method("signtransaction", [result])
                        if signed:
                            broadcast = self.call_method("broadcast", [signed])
                            if broadcast:
                                logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                                logger.info(f"트랜잭션 ID: {broadcast}")
                                return
                except Exception as e:
                    logger.error(f"3차 시도 실패: {str(e)}")
                
                # 4차 시도: sweep 명령어의 올바른 형식으로 시도
                logger.info(f"4차 시도: sweep 명령어 사용 (주소: {PAYOUT_WALLET})")
                try:
                    # 대안: paytomany를 사용하여 전체 잔액 sweep
                    # 주소와 금액의 딕셔너리 형태로 전달: {"address": amount}
                    # 잔액의 90%만 전송하여 수수료 해결
                    amount_to_send = confirmed_bch * 0.9
                    output_dict = {PAYOUT_WALLET: str(amount_to_send)}
                    sweep_result = self.call_method("paytomany", [output_dict])
                    
                    if sweep_result:
                        # 트랜잭션 서명 및 브로드캐스트
                        sweep_signed = self.call_method("signtransaction", [sweep_result])
                        if sweep_signed:
                            sweep_broadcast = self.call_method("broadcast", [sweep_signed])
                            if sweep_broadcast:
                                logger.info(f"paytomany를 통한 자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
                                logger.info(f"트랜잭션 ID: {sweep_broadcast}")
                                return
                except Exception as sweep_error:
                    logger.error(f"4차 시도 실패: {str(sweep_error)}")
                    logger.error(traceback.format_exc())
                
                # 모든 시도가 실패했음을 로그로 남김
                logger.error("모든 자금 전송 시도 실패")
        except Exception as e:
            logger.error(f"자금 전송 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())

def setup_electron_cash_auth():
    """ElectronCash 인증 설정"""
    # 환경 변수에서 설정 가져오기
    rpc_user = os.environ.get('ELECTRON_CASH_USER', 'bchrpc')
    rpc_password = os.environ.get('ELECTRON_CASH_PASSWORD', '')
    
    # 인증 정보 설정
    if not rpc_password:
        # 무작위 비밀번호 생성
        import random
        import string
        rpc_password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
        logger.info(f"ElectronCash RPC 인증을 위한 무작위 비밀번호 생성: {rpc_password}")
    
    # 환경 변수 설정
    os.environ['ELECTRON_CASH_USER'] = rpc_user
    os.environ['ELECTRON_CASH_PASSWORD'] = rpc_password
    
    # Docker 컨테이너 IP 주소 직접 지정
    os.environ['ELECTRON_CASH_URL'] = 'http://electron-cash:7777'
    logger.info(f"ElectronCash URL을 서비스 이름으로 설정: {os.environ['ELECTRON_CASH_URL']}")
    
    # 글로벌 변수 업데이트
    global ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD, ELECTRON_CASH_URL
    ELECTRON_CASH_USER = rpc_user
    ELECTRON_CASH_PASSWORD = rpc_password
    ELECTRON_CASH_URL = os.environ['ELECTRON_CASH_URL']
    
    return rpc_user, rpc_password

def init_electron_cash():
    """ElectronCash 초기화"""
    logger.info("ElectronCash 초기화 중...")
    try:
        # Mock 모드에서는 실제 초기화를 건너뜀
        if MOCK_MODE:
            logger.info("Mock 모드 활성화됨: ElectronCash 초기화 건너뜀")
            return True
            
        try:
            # ElectronCash Python 라이브러리 초기화 시도
            from electroncash import SimpleConfig, Network, Wallet
            logger.info("ElectronCash 모듈 로드 성공")
        except ImportError as e:
            logger.error(f"ElectronCash 초기화 오류: {e}")
            logger.info("ElectronCash 클라이언트를 사용한 RPC 호출을 시도합니다.")
        
        # 지갑 연결 테스트 - 더 안정적인 방법으로 수정
        logger.info("ElectronCash 연결 테스트 중...")
        
        # 간단한 연결 테스트부터 시작
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = electron_cash.call_method("getbalance")
                if result is not None:
                    logger.info(f"ElectronCash 연결 성공 (시도 {attempt + 1}): 잔액 {result}")
                    return True
                else:
                    logger.warning(f"ElectronCash 연결 시도 {attempt + 1} 실패, 재시도 중...")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            except Exception as e:
                logger.warning(f"ElectronCash 연결 시도 {attempt + 1} 오류: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        logger.error("ElectronCash 연결 실패")
        return False
        
    except Exception as e:
        logger.error(f"ElectronCash 초기화 오류: {str(e)}")
        return False

def debug_electron_cash_connection(client):
    """ElectronCash 연결 디버깅"""
    try:
        # 연결 테스트
        logger.info("ElectronCash 연결 테스트 중...")
        
        # 1. 지갑 로드 확인
        wallet_loaded = client.call_method("getinfo")
        if not wallet_loaded:
            logger.error("ElectronCash 지갑이 로드되지 않았습니다.")
            # 지갑 로드 시도
            load_result = client.call_method("load_wallet")
            logger.info(f"지갑 로드 시도 결과: {load_result}")
            
        # 2. 새 주소 생성 테스트
        logger.info("새 주소 생성 테스트 중...")
        test_address = client.call_method("getunusedaddress")
        if test_address:
            logger.info(f"새 주소 생성 성공: {test_address}")
        else:
            logger.error("새 주소 생성 실패")
            
        # 3. 잔액 확인 테스트
        balance = client.call_method("getbalance")
        logger.info(f"지갑 잔액: {balance}")
        
        return True
    except Exception as e:
        logger.error(f"ElectronCash 연결 디버깅 중 오류 발생: {str(e)}")
        return False

# 클라이언트 인스턴스 생성
electron_cash = ElectronCashClient()

# ElectronCash 인증 설정
setup_electron_cash_auth()

# ElectronCash 모듈 초기화
if EC_AVAILABLE:
    init_electron_cash()

# 연결 테스트
debug_electron_cash_connection(electron_cash)