# AI Service - Phân Tích CV

`ai_service` là microservice Python dùng để phân tích nội dung CV cho hệ thống AI Resume System. Service này nhận text CV từ `backend_cv`, gọi nhà cung cấp mô hình AI và trả về JSON có cấu trúc để backend lưu vào database.

## Mục Tiêu

- Nhận nội dung CV đã được backend parse từ file PDF/DOC/DOCX.
- Nhận danh sách ngành nghề và kỹ năng đang có trong hệ thống.
- Gọi LLM provider như Groq, Gemini hoặc GLM.
- Chuẩn hóa kết quả phân tích CV thành JSON.
- Trả về điểm chất lượng CV, kỹ năng match, kinh nghiệm, học vấn, dự án, điểm mạnh, điểm yếu và gợi ý cải thiện.
- Hỗ trợ fallback provider hoặc fallback rule-based khi AI provider lỗi.

## Kiến Trúc Hiện Tại

Service hiện là một Python microservice nhỏ:

- `api.py`: Starlette app, expose health check và API nội bộ `/internal/cv/analyze`.
- `schemas.py`: Pydantic schema cho request/response.
- `resume_analyzer.py`: logic tạo prompt, gọi AI provider, parse JSON và fallback.
- `llm_client.py`: cấu hình client OpenAI-compatible cho Groq, Gemini và GLM.
- `main.py`: demo Streamlit cũ, không phải flow chính.

Luồng chính:

```txt
backend_cv -> POST /internal/cv/analyze -> ai_service -> LLM Provider -> JSON response -> backend_cv
```

## Công Nghệ Sử Dụng

- Python 3.10+ khuyến nghị
- Starlette
- Uvicorn
- Pydantic
- python-dotenv
- OpenAI Python SDK theo chuẩn OpenAI-compatible API
- Streamlit chỉ dùng cho demo tùy chọn

## Yêu Cầu Cài Đặt

- Python 3.10+
- pip
- Virtual environment
- Ít nhất một API key cho Groq, Gemini hoặc GLM

## Cấu Hình Môi Trường

Tạo file `.env` từ `.env.example`:

```bash
copy .env.example .env
```

Các biến quan trọng:

```env
DEFAULT_PROVIDER=groq
PROVIDER_ORDER=groq,gemini,glm

GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant

GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

GLM_BASE_URL=https://api.z.ai/api/paas/v4
GLM_API_KEY=
GLM_MODEL=GLM-4.5-Flash

AI_SERVICE_API_KEY=internal-shared-secret
AI_ANALYZE_TIMEOUT_MS=30000
AI_MAX_INPUT_CHARS=5000
AI_MAX_SKILLS_FOR_PROMPT=80
```

Lưu ý:

- Chỉ cần có API key của một provider là có thể chạy.
- Provider không có API key sẽ được bỏ qua trong fallback sequence.
- `AI_SERVICE_API_KEY` phải trùng với `backend_cv/.env`.

## Cài Dependency

```bash
cd ai_service
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install uvicorn starlette pydantic python-dotenv openai
```

Nếu dùng demo Streamlit:

```bash
pip install streamlit PyPDF2 pandas
```

## Chạy Development

```bash
uvicorn api:app --host 0.0.0.0 --port 8001 --reload
```

Health check:

```bash
Invoke-WebRequest http://localhost:8001/health
```

API chính:

```txt
POST http://localhost:8001/internal/cv/analyze
Header: x-internal-api-key: internal-shared-secret
```

## Kết Nối Với Backend

Trong `backend_cv/.env` cần cấu hình:

```env
AI_SERVICE_BASE_URL=http://localhost:8001
AI_SERVICE_TIMEOUT_MS=60000
AI_SERVICE_API_KEY=internal-shared-secret
```

Sau đó backend sẽ gọi service này khi worker phân tích CV chạy.

## Demo Streamlit Tùy Chọn

Flow chính của hệ thống không dùng Streamlit. Nếu muốn chạy demo cũ:

```bash
streamlit run main.py
```

## Ghi Chú Vận Hành

- Service chỉ nên được gọi nội bộ bởi backend.
- Nếu trả lỗi `Invalid internal API key`, kiểm tra `AI_SERVICE_API_KEY` hai bên.
- Nếu phân tích thất bại, kiểm tra API key provider và model.
- Nếu provider chính lỗi, service sẽ thử provider tiếp theo theo `PROVIDER_ORDER`.
- Nếu tất cả provider lỗi, service có fallback rule-based để backend vẫn nhận được response cơ bản.
