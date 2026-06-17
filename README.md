# AWS Tabanlı Video Akışı ve İşleme Uygulaması

FastAPI tabanlı, AWS Kinesis Video Streams (KVS) ile video akışı yönetimi ve
AWS Rekognition ile yapay zeka destekli video/frame analizi yapan modüler bir
backend uygulaması.

## İçindekiler

- [Mimari](#mimari)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [AWS Bağlantısının Kurulması](#aws-bağlantısının-kurulması)
- [Veritabanı Kurulumu (PostgreSQL + Alembic)](#veritabanı-kurulumu-postgresql--alembic)
- [Uygulamayı Çalıştırma](#uygulamayı-çalıştırma)
- [API Kullanımı](#api-kullanımı)
- [Testleri Çalıştırma](#testleri-çalıştırma)
- [Sorun Giderme](#sorun-giderme)

## Mimari

```text
video_stream_app/
├── app/
│   ├── api/v1/         # API endpoint'leri (streams, analysis) ve router
│   ├── core/           # config.py, database.py, aws.py (AWS istemcileri)
│   ├── models/         # SQLAlchemy modelleri (db_models.py) ve Pydantic şemaları (schemas.py)
│   ├── services/       # İş mantığı: kinesis_service, rekognition_service, analysis_service
│   ├── utils/           # OpenCV yardımcıları (video_utils.py)
│   └── main.py          # FastAPI uygulama giriş noktası
├── alembic/             # Veritabanı migration'ları
├── tests/               # Pytest test paketi
├── requirements.txt
└── .env.example
```

İş akışı şu şekildedir:

1. `POST /api/v1/streams` ile bir KVS stream'i AWS üzerinde oluşturulur ve
   veritabanına kaydedilir.
2. Video kaynağından (dosya/kamera) `app/utils/video_utils.py` ile frame'ler
   okunur ve JPEG byte dizisine çevrilir (gerçek zamanlı KVS akışı; PutMedia
   gibi ham binary protokol işlemleri genelde AWS KVS Producer SDK/GStreamer
   ile yapılır, bu proje API üzerinden stream yönetimi ve frame analizini
   kapsar).
3. `POST /api/v1/analysis/{stream_id}/analyze-frame` endpoint'ine bir frame
   (görüntü dosyası) gönderilir; bu görüntü AWS Rekognition'a iletilir,
   nesne/etiket (ve isteğe bağlı yüz/duygu) analizleri yapılır ve sonuçlar
   PostgreSQL veritabanına kaydedilir.
4. `GET /api/v1/analysis/{stream_id}/results` ile geçmiş analiz sonuçları
   sorgulanabilir.

## Gereksinimler

- Python 3.10+
- PostgreSQL 13+ (yerel veya AWS RDS)
- Bir AWS hesabı ve aşağıdaki izinlere sahip bir IAM kullanıcısı/rolü:
  - `kinesisvideo:CreateStream`, `DescribeStream`, `DeleteStream`,
    `ListStreams`, `GetDataEndpoint`
  - `rekognition:DetectLabels`, `DetectFaces`

## Kurulum

```bash
git clone <repo-url>
cd video_stream_app

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env   # Windows: copy .env.example .env
```

`.env` dosyasını kendi AWS ve veritabanı bilgilerinizle güncelleyin (aşağıdaki
bölümlere bakın).

## AWS Bağlantısının Kurulması

Uygulama AWS servislerine **boto3** üzerinden bağlanır (`app/core/aws.py`).
İki yoldan biriyle kimlik doğrulama yapabilirsiniz:

### Seçenek 1 — `.env` dosyası ile Access Key (yerel geliştirme için)

1. AWS Console → IAM → Users → kullanıcı oluşturun (veya mevcut kullanıcıyı
   kullanın) ve yukarıdaki Kinesis/Rekognition izinlerini içeren bir policy
   ekleyin.
2. "Security credentials" sekmesinden bir **Access Key** oluşturun.
3. `.env` dosyasına yazın:

   ```env
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=eu-central-1
   ```

`app/core/config.py` bu değerleri okuyup `app/core/aws.py` içindeki boto3
istemcilerine aktarır.

### Seçenek 2 — AWS CLI kimlik bilgileri / IAM Role (önerilen, production)

`.env` dosyasında `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` **boş**
bırakılırsa, boto3 otomatik olarak standart kimlik bilgisi zincirine
(`~/.aws/credentials`, ortam değişkenleri, EC2/ECS Instance Profile veya
IAM Role) düşer. Bu, access key'lerin koda/`.env`'e gömülmesini önlediği için
production ortamında tercih edilmelidir:

```bash
aws configure
# AWS Access Key ID, Secret Key, Region (eu-central-1) ve output format girilir
```

### KVS Stream'i Doğrulama

Bağlantıyı test etmek için:

```bash
aws kinesisvideo list-streams --region eu-central-1
```

### Rekognition Erişimini Doğrulama

```bash
aws rekognition describe-collection --collection-id test 2>&1 | head -5
# "ResourceNotFoundException" hatası alıyorsanız kimlik doğrulama/izinler doğrudur,
# sadece "test" koleksiyonu yoktur.
```

## Veritabanı Kurulumu (PostgreSQL + Alembic)

1. Yerel bir PostgreSQL veritabanı oluşturun:

   ```bash
   createdb video_stream_db
   ```

   Ya da AWS RDS üzerinde bir PostgreSQL instance'ı oluşturup `.env` içindeki
   `DATABASE_URL`'i RDS endpoint'ine göre güncelleyin:

   ```env
   DATABASE_URL=postgresql+psycopg2://<kullanici>:<sifre>@<rds-endpoint>:5432/video_stream_db
   ```

2. Migration'ları uygulayın:

   ```bash
   alembic upgrade head
   ```

   Bu komut `streams` ve `analysis_results` tablolarını oluşturur.

## Uygulamayı Çalıştırma

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Uygulama ayağa kalktığında:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Sağlık kontrolü: `GET /health`

## API Kullanımı

### 1. Yeni bir stream oluştur

```bash
curl -X POST http://localhost:8000/api/v1/streams \
  -H "Content-Type: application/json" \
  -d '{"name": "kamera-1"}'
```

Bu çağrı AWS KVS üzerinde gerçek bir stream oluşturur ve dönen `id` değerini
sonraki adımlarda kullanırsınız.

### 2. Stream'leri listele

```bash
curl http://localhost:8000/api/v1/streams
```

### 3. Bir frame'i analiz et

Yerel bir görüntü dosyasını (örn. bir video dosyasından OpenCV ile alınmış
frame ya da doğrudan bir JPEG) Rekognition ile analiz ettirin:

```bash
curl -X POST "http://localhost:8000/api/v1/analysis/<stream_id>/analyze-frame?include_faces=true" \
  -F "file=@frame.jpg"
```

Yanıt, tespit edilen etiketleri/yüzleri ve güven (confidence) skorlarını
içerir; aynı zamanda veritabanına kaydedilir.

### 4. Geçmiş analiz sonuçlarını getir

```bash
curl http://localhost:8000/api/v1/analysis/<stream_id>/results
```

### 5. Stream'i durdur / sil

```bash
curl -X POST http://localhost:8000/api/v1/streams/<stream_id>/stop
curl -X DELETE http://localhost:8000/api/v1/streams/<stream_id>
```

### Video dosyasından frame üretme (yerel test)

`app/utils/video_utils.py` içindeki `iter_video_frames` / `read_single_frame`
fonksiyonları, bir video dosyasından veya web kamerasından (`source=0`)
OpenCV ile frame okuyup `frame_to_jpeg_bytes` ile JPEG byte dizisine
çevirmenizi sağlar. Bu byte dizisi doğrudan `analyze-frame` endpoint'ine
gönderilebilir; gerçek zamanlı bir entegrasyonda bu döngü periyodik olarak
(örn. her N. frame) çalıştırılır.

## Testleri Çalıştırma

Testler gerçek AWS çağrıları yapmaz; `boto3` servis metodları `monkeypatch`
ile sahtelenir ve veritabanı işlemleri SQLite in-memory üzerinde çalışır:

```bash
pytest -q
```

## Sorun Giderme

- **`NoCredentialsError` / `Unable to locate credentials`**: `.env` dosyanızda
  access key tanımlı değilse ve `aws configure` çalıştırılmadıysa bu hata
  alınır. [AWS Bağlantısının Kurulması](#aws-bağlantısının-kurulması) adımını
  tekrar kontrol edin.
- **`ResourceInUseException` (stream oluşturma)**: Aynı isimde bir KVS stream
  zaten mevcuttur; servis bu durumda var olan stream'in ARN'ini otomatik
  olarak kullanır.
- **`psycopg2` kurulum hatası**: Sisteminizde PostgreSQL geliştirme
  başlıkları yoksa `psycopg2-binary` paketinin önceden derlenmiş (wheel)
  sürümünün kurulduğundan emin olun (`pip install psycopg2-binary`).
- **Rekognition `InvalidImageFormatException`**: Gönderilen dosyanın geçerli
  bir JPEG/PNG olduğundan ve boyutunun AWS limitlerini (5MB, senkron API)
  aşmadığından emin olun.
