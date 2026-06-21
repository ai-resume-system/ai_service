# AI Service - Dịch Vụ Phân Tích CV

`ai_service` là microservice Python dùng trong hệ thống AI Resume System. Service này nhận nội dung CV đã được backend trích xuất, gửi prompt tới nhà cung cấp mô hình AI và trả về kết quả phân tích CV theo JSON chuẩn để `backend_cv` lưu vào database.

Flow chính của hệ thống là:

```txt
frontend_cv
        -> backend_cv
        -> ai_service /internal/cv/analyze
        -> LLM Provider Groq/Gemini/GLM
        -> JSON analysis response
        -> backend_cv lưu cv_parsed_data và cv_skills
```

`main.py` Streamlit chỉ còn là demo phụ, không nằm trong flow chính của hệ thống.

## Mục Tiêu

- Nhận raw text của CV từ `backend_cv`.
- Nhận danh sách career category và skill đang active trong hệ thống.
- Gọi LLM provider theo chuẩn OpenAI-compatible API.
- Trả kết quả phân tích CV theo cấu trúc JSON nghiêm ngặt.
- Match skill trong CV với skill hệ thống dựa trên `slug`, `name`, `aliases`.
- Gợi ý career category phù hợp từ danh sách backend gửi sang.
- Tính điểm chất lượng CV và breakdown theo nhiều tiêu chí.
- Fallback sang provider khác nếu provider chính lỗi.
- Fallback rule-based nếu toàn bộ provider AI lỗi để backend vẫn nhận được response cơ bản.

## Thành Phần Source

- `api.py`: Starlette app, định nghĩa `/health` và `/internal/cv/analyze`.
- `schemas.py`: Pydantic schema cho request/response.
- `resume_analyzer.py`: tạo prompt, gọi AI, parse JSON, validate response và fallback rule-based.
- `llm_client.py`: cấu hình provider Groq, Gemini, GLM.
- `main.py`: demo Streamlit cũ để upload PDF và xem phân tích nhanh.
- `.env.example`: mẫu biến môi trường.
- `lenh_chay.txt`: ghi chú lệnh chạy nhanh theo flow chính.

## API Chính

### Health check

```txt
GET /health
```

Response:

```json
{
  "status": true,
  "service": "ai_service"
}
```

### Phân tích CV nội bộ

```txt
POST /internal/cv/analyze
Header: x-internal-api-key: internal-shared-secret
```

API này chỉ nên được gọi bởi `backend_cv`.

Request chính:

```json
{
  "cvId": "uuid-or-demo-id",
  "rawText": "Noi dung CV da parse",
  "fileExtension": "pdf",
  "requestedProvider": "groq",
  "availableCareerCategories": [
    {
      "name": "Cong nghe thong tin",
      "slug": "cong-nghe-thong-tin"
    }
  ],
  "availableSkills": [
    {
      "name": "React",
      "slug": "react",
      "careerCategorySlug": "cong-nghe-thong-tin",
      "aliases": ["reactjs", "react.js"]
    }
  ]
}
```

Response trả về trong field `data`, gồm các nhóm chính:

- `summary`
- `resumeQualityScore`
- `scoreBreakdown`
- `primaryRole`
- `seniorityLevel`
- `careerCategorySuggestion`
- `matchedSkills`
- `otherDetectedSkills`
- `keywords`
- `relatedJobTitles`
- `strengths`
- `weaknesses`
- `improvementSuggestions`
- `education`
- `experience`
- `projects`
- `atsNotes`
- `provider`
- `model`
- `confidenceFlags`
- `promptVersion`
- `analyzedAt`

## Công Nghệ Sử Dụng

- Python 3.10+ khuyến nghị
- Starlette
- Uvicorn
- Pydantic
- python-dotenv
- OpenAI Python SDK
- Groq/Gemini/GLM qua OpenAI-compatible endpoint
- Streamlit, PyPDF2, pandas cho demo tùy chọn

## Yêu Cầu Cài Đặt

- Python 3.10+
- pip
- Virtual environment
- Ít nhất một API key trong các provider: Groq, Gemini hoặc GLM
- `backend_cv` nếu muốn test full flow từ hệ thống chính

## Cài Đặt Môi Trường

Di chuyển vào thư mục service:

```powershell
cd ai_service
```

Tạo virtual environment nếu máy chưa có:

```powershell
py -m venv venv
```

Kích hoạt environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Cài thư viện tối thiểu cho flow chính:

```powershell
pip install uvicorn starlette pydantic python-dotenv openai
```

Nếu muốn chạy demo Streamlit cũ:

```powershell
pip install streamlit PyPDF2 pandas
```

## Cấu Hình `.env`

Tạo file `.env` từ `.env.example`:

```powershell
copy .env.example .env
```

Giá trị tối thiểu:

```env
DEFAULT_PROVIDER=groq
PROVIDER_ORDER=groq,gemini,glm

GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.1-8b-instant

GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash

GLM_BASE_URL=https://api.z.ai/api/paas/v4
GLM_API_KEY=your_glm_key
GLM_MODEL=GLM-4.5-Flash

AI_SERVICE_API_KEY=internal-shared-secret
AI_ANALYZE_TIMEOUT_MS=30000
AI_MAX_INPUT_CHARS=5000
AI_MAX_SKILLS_FOR_PROMPT=80
```

Ghi chú:

- Chỉ cần một provider có API key là service có thể chạy.
- `GROQ_MODEL`, `GEMINI_MODEL`, `GLM_MODEL` có default, chỉ cần đổi khi muốn dùng model khác.
- `PROVIDER_ORDER=groq,gemini,glm` nghĩa là service thử Groq trước, nếu lỗi hoặc không có key thì thử Gemini, sau đó GLM.
- Provider nào không có API key sẽ được bỏ qua.
- `AI_SERVICE_API_KEY` dùng để bảo vệ API nội bộ, phải trùng với `backend_cv/.env`.

## Cấu Hình Backend Kết Nối AI Service

Trong `backend_cv/.env`, cấu hình:

```env
AI_SERVICE_BASE_URL=http://localhost:8001
AI_SERVICE_TIMEOUT_MS=60000
AI_SERVICE_API_KEY=internal-shared-secret
```

`AI_SERVICE_API_KEY` ở backend và AI service phải giống nhau.

## Chạy Service

Chạy API nội bộ cho backend:

```powershell
uvicorn api:app --host 0.0.0.0 --port 8001 --reload
```

URL local:

```txt
http://localhost:8001
```

## Health Check

```powershell
Invoke-WebRequest http://localhost:8001/health
```

Kỳ vọng nhận response có:

```json
{
  "status": true,
  "service": "ai_service"
}
```

## Test Trực Tiếp API Phân Tích

Chạy lệnh PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/internal/cv/analyze `
  -Headers @{ "x-internal-api-key" = "internal-shared-secret" } `
  -ContentType "application/json" `
  -Body '{
    "cvId":"demo-cv-001",
    "rawText":"Thuc tap sinh lap trinh web co kinh nghiem React, Laravel, MySQL va Git.",
    "fileExtension":"pdf",
    "requestedProvider":"groq",
    "availableCareerCategories":[
      {"name":"Cong nghe thong tin","slug":"cong-nghe-thong-tin"},
      {"name":"Luat","slug":"luat"},
      {"name":"Ke toan","slug":"ke-toan"}
    ],
    "availableSkills":[
      {"name":"React","slug":"react","careerCategorySlug":"cong-nghe-thong-tin","aliases":["reactjs","react.js"]},
      {"name":"Laravel","slug":"laravel","careerCategorySlug":"cong-nghe-thong-tin","aliases":[]},
      {"name":"MySQL","slug":"mysql","careerCategorySlug":"cong-nghe-thong-tin","aliases":[]},
      {"name":"Git","slug":"git","careerCategorySlug":"cong-nghe-thong-tin","aliases":[]}
    ]
  }'
```

Nếu test trực tiếp API pass thì mới test tiếp full flow từ `backend_cv`.

## Test Full Flow Từ Backend

Sau khi AI service chạy:

1. Chạy hạ tầng PostgreSQL, Redis, MinIO.
2. Chạy `backend_cv`.
3. Upload CV như flow hiện tại.
4. Gọi:

```txt
POST /api/v1/cvs/:id/analyze
```

5. Poll kết quả:

```txt
GET /api/v1/cvs/:id/analysis
```

Nếu thành công, backend sẽ lưu kết quả vào:

- `cv_parsed_data`
- `cv_skills`

## Test Fallback Provider

Ví dụ muốn test fallback từ Groq sang Gemini hoặc GLM:

1. Tạm thời để trống `GROQ_API_KEY`.
2. Đảm bảo `GEMINI_API_KEY` hoặc `GLM_API_KEY` có giá trị.
3. Restart uvicorn.
4. Gọi lại `/internal/cv/analyze`.
5. Kiểm tra log để xem provider tiếp theo được sử dụng.

Nếu toàn bộ provider lỗi, service dùng rule-based fallback và thêm flag:

```txt
rule_based_fallback_used
provider_fallback_exhausted
```

## Demo Streamlit Tùy Chọn

Streamlit không nằm trong flow chính. Nếu vẫn muốn xem demo upload PDF và phân tích thủ công:

```powershell
streamlit run main.py
```

## Lỗi Thường Gặp

### `Invalid internal API key`

Nguyên nhân:

- Header `x-internal-api-key` không trùng `AI_SERVICE_API_KEY`.
- `backend_cv/.env` và `ai_service/.env` đặt key khác nhau.

Cách xử lý:

- Đồng bộ `AI_SERVICE_API_KEY` ở cả hai service.
- Restart backend và AI service sau khi đổi `.env`.

### `No LLM API keys configured in .env`

Nguyên nhân:

- Không có provider nào được cấu hình API key.

Cách xử lý:

- Điền ít nhất một key: `GROQ_API_KEY`, `GEMINI_API_KEY` hoặc `GLM_API_KEY`.

### Model không trả JSON hợp lệ

Nguyên nhân:

- Provider trả text không đúng JSON.
- Model lỗi hoặc bị timeout.

Cách xử lý:

- Kiểm tra log.
- Thử provider khác bằng `requestedProvider`.
- Tăng `AI_ANALYZE_TIMEOUT_MS` nếu cần.

### Backend gọi AI service bị timeout

Nguyên nhân:

- AI service chưa chạy.
- Sai `AI_SERVICE_BASE_URL`.
- Provider phản hồi chậm.

Cách xử lý:

- Kiểm tra `http://localhost:8001/health`.
- Kiểm tra `AI_SERVICE_BASE_URL=http://localhost:8001`.
- Tăng `AI_SERVICE_TIMEOUT_MS` ở backend hoặc `AI_ANALYZE_TIMEOUT_MS` ở AI service.

## Ghi Chú Vận Hành

- Đây là service nội bộ, không nên public trực tiếp ra internet.
- Backend gửi danh sách category/skill sang AI service để AI không tự bịa ID hoặc category ngoài hệ thống.
- AI service không ghi database; backend mới là nơi lưu kết quả phân tích.
- `rawText` được cắt theo `AI_MAX_INPUT_CHARS` để tránh prompt quá dài.
- Kết quả phân tích CV là điểm chất lượng CV, không phải điểm phù hợp với job.
- Điểm phù hợp CV-job được backend tính riêng dựa trên `cv_skills`, `job_skills` và dữ liệu phân tích đã lưu.
