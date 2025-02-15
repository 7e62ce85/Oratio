use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;

// 결제 청구서(인보이스) 구조체 (실제 API 스펙에 맞게 수정)
#[derive(Serialize, Deserialize, Debug, Clone)]
struct PaymentInvoice {
    invoice_id: String,
    payment_address: String,
    amount: f64,  // 예: 0.005 BCH
    status: String, // "pending", "paid" 등
}

// 결제 콜백(완료 알림)에서 받게 될 데이터 구조체
#[derive(Serialize, Deserialize, Debug)]
struct PaymentCallback {
    invoice_id: String,
    status: String, // "paid" 등 상태
    txid: String,
}

// 간단하게 청구서를 저장하는 장소(멤버 리스트) - 실제 서비스에서는 DB 연동 권장
struct AppState {
    invoices: Mutex<Vec<PaymentInvoice>>,
}

// 청구서 인보이스 생성 (실제로는 BCH 결제 API를 호출해야 함)
async fn generate_invoice(state: web::Data<AppState>) -> impl Responder {
    // 여기서는 고정된 값(예시)로 청구서를 만들어봐
    let invoice = PaymentInvoice {
        invoice_id: "invoice123".to_string(),// 실제로는 랜덤하게 만들어야 해 (예: UUID)
        payment_address: "bitcoincash:qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w".to_string(),// 실제 주소로 바꾸기
        amount: 0.005,
        status: "pending".to_string(),
    };
    // 청구서를 저장해두자.
    {
        let mut invoices = state.invoices.lock().unwrap();
        invoices.push(invoice.clone());
    }
    // 청구서 정보를 JSON으로 응답
    HttpResponse::Ok().json(invoice)
}

// 결제 완료 알림을 처리하는 함수
async fn payment_callback(
    state: web::Data<AppState>,
    callback: web::Json<PaymentCallback>,
) -> impl Responder {
    println!("결제 콜백 받음: {:?}", callback);
   
    let mut updated = false;
    {
        let mut invoices = state.invoices.lock().unwrap();
        // 저장된 청구서 중에서 invoice_id가 같은 것을 찾아 상태 업데이트
        for inv in invoices.iter_mut() {
            if inv.invoice_id == callback.invoice_id && callback.status == "paid" {
                inv.status = "paid".to_string();
                updated = true;
                println!("업데이트된 청구서: {:?}", inv);
                break;
            }
        }
    }

    if updated {
        HttpResponse::Ok().body("결제 완료, 상태 업데이트")
    } else {
        HttpResponse::BadRequest().body("결제 검증 실패 또는 잘못된 상태")
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // 앱 상태(청구서 목록)를 초기화
    let app_state = web::Data::new(AppState {
        invoices: Mutex::new(Vec::new()),
    });
    // 서버 시작! 0.0.0.0:8081 포트에서 듣고 있음.
    HttpServer::new(move || {
        App::new()
            .app_data(app_state.clone())
            .route("/generate_invoice", web::get().to(generate_invoice))
            .route("/payment_callback", web::post().to(payment_callback))
    })
    // 내부 포트는 임의로 8081 사용
    .bind("0.0.0.0:8081")?
    .run()
    .await
}
