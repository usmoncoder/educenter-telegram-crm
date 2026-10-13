# EduCenter Telegram CRM

O'quv markazlari, til maktablari va IT akademiyalar uchun Telegram userbot va CRM tizimi.

Tizim markazning **o'z Telegram akkauntiga** (telefon raqamli oddiy akkaunt) ulanadi va:

1. **Yangi mijozga avtomatik ma'lumot yuboradi** — mijoz birinchi marta yozganda kurslar, narxlar, manzil haqidagi oldindan yozilgan xabar bir marta yuboriladi.
2. **Javobsiz murojaatlarni nazorat qiladi** — mijoz yozganidan keyin 5 daqiqa ichida operator javob bermasa, rahbarlarga ogohlantirish yuboriladi va murojaat dashboard'da qizil bilan ko'rsatiladi. Avtomatik xabar javob hisoblanmaydi.
3. **Guruhlarga e'lon yuboradi** — tanlangan Telegram guruhlariga darhol, belgilangan vaqtda yoki har kuni/haftada.
4. **Veb-panel** — o'zbek tilidagi dashboard: mijozlar, suhbatlar, javobsiz murojaatlar, e'lonlar, hisobotlar, xodimlar va audit jurnali.

> Tizim faqat siz egalik qiladigan akkaunt va a'zo bo'lgan guruhlar bilan ishlaydi. U spam, ommaviy
> tarqatish yoki ruxsatsiz kuzatuv uchun mo'ljallanmagan: guruhga faqat administrator aniq yoqqan
> va akkaunt yozish huquqiga ega bo'lgan joyga yoziladi.

---

## Mundarija

1. [Arxitektura](#1-arxitektura)
2. [Tizim talablari](#2-tizim-talablari)
3. [Telegram API kalitlarini olish](#3-telegram-api-kalitlarini-olish)
4. [Muhit o'zgaruvchilari (.env)](#4-muhit-ozgaruvchilari-env)
5. [Docker Compose bilan o'rnatish (tavsiya etiladi)](#5-docker-compose-bilan-ornatish-tavsiya-etiladi)
6. [Birinchi Super Admin'ni yaratish](#6-birinchi-super-adminni-yaratish)
7. [Telegram akkauntiga ulanish](#7-telegram-akkauntiga-ulanish)
8. [Docker'siz ishga tushirish (dasturchilar uchun)](#8-dockersiz-ishga-tushirish-dasturchilar-uchun)
9. [Avtomatik javobni sozlash](#9-avtomatik-javobni-sozlash)
10. [5 daqiqalik nazorat (SLA) qanday ishlaydi](#10-5-daqiqalik-nazorat-sla-qanday-ishlaydi)
11. [Administratorlarga ogohlantirish](#11-administratorlarga-ogohlantirish)
12. [Guruhlar va rejalashtirilgan e'lonlar](#12-guruhlar-va-rejalashtirilgan-elonlar)
13. [Rollar va kirish huquqlari](#13-rollar-va-kirish-huquqlari)
14. [Testlarni ishga tushirish](#14-testlarni-ishga-tushirish)
15. [Loglar va muammolarni hal qilish](#15-loglar-va-muammolarni-hal-qilish)
16. [Zaxira nusxa va tiklash](#16-zaxira-nusxa-va-tiklash)
17. [Sessiya va maxfiy ma'lumotlarni himoyalash](#17-sessiya-va-maxfiy-malumotlarni-himoyalash)
18. [Nima tayyor, nima tashqi sozlash talab qiladi, cheklovlar](#18-nima-tayyor-nima-tashqi-sozlash-talab-qiladi-cheklovlar)

Qo'shimcha hujjatlar (ingliz tilida, dasturchilar uchun):
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — dizayn qarorlari, ma'lumotlar bazasi, holat mashinalari;
[`docs/SECURITY.md`](docs/SECURITY.md) — production tekshiruv ro'yxati.

---

## 1. Arxitektura

```
              HTTPS reverse proxy (Caddy / nginx)        ← siz sozlaysiz
                          │
                ┌─────────▼─────────┐
                │  web (nginx)      │  React dashboard + /api proxy
                └─────────┬─────────┘
                          │ /api
                ┌─────────▼─────────┐        ┌─────────────────────┐
                │  api (FastAPI)    │        │  worker (Telethon)  │◄──► Telegram MTProto
                │  Telegram'ga      │        │  yagona Telegram     │
                │  ulanmaydi        │        │  ulanishi + fon      │
                └─────────┬─────────┘        │  jarayonlar          │
                          │                  └──────────┬──────────┘
                          └──────────► PostgreSQL ◄─────┘
```

| Komponent | Vazifasi |
|---|---|
| `api` | Veb-panel API: autentifikatsiya, rollar, CRUD, hisobotlar. **Telegram kalitlari va sessiyasiga ega emas.** |
| `worker` | Telegram akkauntiga ulangan yagona jarayon: xabarlarni qabul qiladi, avtomatik javob, SLA ogohlantirishlari, e'lonlar va paneldan yozilgan javoblarni yuboradi. |
| `db` | PostgreSQL 16 — barcha holat shu yerda (mijozlar, murojaatlar, rejalar, yuborishlar tarixi). |
| `web` | nginx: tayyor React ilovasini beradi va `/api` so'rovlarini `api`ga uzatadi. |
| `migrate` | Ishga tushishda Alembic migratsiyalarini qo'llaydi va to'xtaydi. |

API va worker faqat ma'lumotlar bazasi orqali "gaplashadi": panelda «Guruhlarni yangilash» yoki «Javob yuborish»
bosilganda API bazaga vazifa yozadi, worker uni bajaradi va **haqiqiy natijani** qaytaradi. Shu sababli panel hech
qachon Telegram tasdiqlamagan xabarni "yuborildi" deb ko'rsatmaydi.

**Texnologiyalar:** Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, Telethon 1.45 (MTProto),
React 19 + TypeScript + Vite + Tailwind CSS 4, TanStack Query, Docker Compose.

## 2. Tizim talablari

- Linux server (1 vCPU, 1 GB RAM yetarli), Docker Engine 24+ va Docker Compose v2.
- Domen va HTTPS (masalan, Caddy yoki nginx + Let's Encrypt) — production uchun majburiy.
- Markazning Telegram akkaunti (telefon raqam, SMS/Telegram kodi va yoqilgan bo'lsa 2FA paroli).

Docker'siz ishlab chiqish uchun: Python 3.12+, Node.js 22+, PostgreSQL 16.

## 3. Telegram API kalitlarini olish

1. <https://my.telegram.org> saytiga markaz akkauntining telefon raqami bilan kiring.
2. **API development tools** bo'limini oching.
3. Ilova yarating (nom: masalan `EduCenter CRM`, platforma: `Other`).
4. `App api_id` va `App api_hash` qiymatlarini `.env` fayliga yozing.

`api_hash` — maxfiy kalit. Uni hech kimga bermang, git'ga qo'shmang, chatga yubormang.

## 4. Muhit o'zgaruvchilari (.env)

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

| O'zgaruvchi | Tavsif |
|---|---|
| `ENVIRONMENT` | `production` (xavfsiz cookie, API hujjatlari yopiq) yoki `development` |
| `POSTGRES_PASSWORD` | Ma'lumotlar bazasi paroli — uzun tasodifiy qiymat: `openssl rand -base64 32` |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | 3-bo'limda olingan kalitlar |
| `TELEGRAM_PHONE` | Ixtiyoriy: kirish ustasi so'ramasligi uchun telefon raqam |
| `ALERT_BOT_TOKEN` | Ixtiyoriy: ogohlantirishlarni alohida bot orqali yuborish uchun (11-bo'lim) |
| `WEB_BIND`, `WEB_PORT` | Panel qaysi manzilda ochiladi (standart `127.0.0.1:8080`) |
| `TRUSTED_PROXY_COUNT` | API oldidagi proxy'lar soni: `web` = 1, oldida HTTPS proxy bo'lsa 2 |
| `SESSION_TTL_HOURS` | Panel sessiyasi muddati (soat) |

Barcha o'zgaruvchilar izohlari bilan `.env.example` faylida.

## 5. Docker Compose bilan o'rnatish (tavsiya etiladi)

```bash
git clone <repo> /opt/educenter-crm && cd /opt/educenter-crm
cp .env.example .env && chmod 600 .env     # qiymatlarni to'ldiring
docker compose up -d --build               # yoki: make up
docker compose ps                          # barcha servislar "healthy"/"running" bo'lishi kerak
```

`migrate` servisi ma'lumotlar bazasini avtomatik yaratadi va migratsiyalarni qo'llaydi (keyin `exited (0)` holatida
qoladi — bu normal). Migratsiyani qo'lda qo'llash: `docker compose run --rm migrate` yoki `make migrate`.

Panel `http://127.0.0.1:8080` manzilida. Production'da uni HTTPS orqali oching, masalan Caddy bilan
(`/etc/caddy/Caddyfile`):

```
crm.markaz.uz {
    reverse_proxy 127.0.0.1:8080
}
```

HTTPS proxy qo'shganda `.env` da `TRUSTED_PROXY_COUNT=2` qiling.

## 6. Birinchi Super Admin'ni yaratish

Tizimda standart parol yo'q. Birinchi administrator serverda bir marta yaratiladi:

```bash
docker compose run --rm api python -m app.cli create-superadmin --username admin --full-name "Ism Familiya"
# yoki: make superadmin
```

Parol terminalda so'raladi (ekranda ko'rinmaydi, shell tarixiga tushmaydi). Talab: kamida 12 belgi; kichik va katta
harf, raqam, belgilardan kamida uchtasi. Qolgan xodimlar panelning **Administratorlar** bo'limida yaratiladi.

Parolni unutsangiz:

```bash
docker compose run --rm api python -m app.cli reset-password --username admin
```

## 7. Telegram akkauntiga ulanish

Kirish kodi va 2FA paroli **veb-panelda so'ralmaydi va hech qayerda saqlanmaydi**. Kirish serverda bir martalik
terminal ustasi orqali bajariladi:

```bash
docker compose stop worker
docker compose run --rm worker python -m app.telegram.auth_cli
docker compose start worker
# yoki hammasi bitta buyruqda: make tg-login
```

Usta telefon raqamni, Telegram yuborgan kodni va (yoqilgan bo'lsa) 2FA parolini so'raydi. Muvaffaqiyatli
kirgach, sessiya `tgsession` Docker volume'ida saqlanadi va server qayta ishga tushganda qayta ishlatiladi.
**Telegram ulanishi** sahifasida holat bir daqiqa ichida «Telegram ulangan»ga o'zgaradi.

- Worker'ni to'xtatish shart: bitta sessiya faylini ikki jarayon bir vaqtda ishlatmasligi kerak.
- Sessiya yaroqsiz bo'lib qolsa (masalan, Telegram'da «Barcha seanslarni yakunlash» bosilgan), panel
  «Kirish talab qilinadi» deb ko'rsatadi — yuqoridagi buyruqni qayta bajaring.
- Panelda **Qayta ulanish** tugmasi (Super Admin) worker'ni Telegram'ga qaytadan ulaydi.
- Sessiyani butunlay yakunlash: `make tg-logout`.

## 8. Docker'siz ishga tushirish (dasturchilar uchun)

```bash
# 1. PostgreSQL bazasini yarating
sudo -u postgres psql -c "CREATE USER educenter WITH PASSWORD 'educenter';"
sudo -u postgres psql -c "CREATE DATABASE educenter OWNER educenter;"
sudo -u postgres psql -c "CREATE DATABASE educenter_test OWNER educenter;"

# 2. Bog'liqliklar
make dev-install            # .venv + backend[dev] + npm ci

# 3. Sozlamalar (backend/.env yoki muhit o'zgaruvchilari)
export DATABASE_URL=postgresql+asyncpg://educenter:educenter@localhost:5432/educenter
export ENVIRONMENT=development LOG_JSON=false

# 4. Migratsiyalar va administrator
cd backend && ../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.cli create-superadmin --username admin
cd ..

# 5. Uchta terminalda:
make dev-api                # API      → http://127.0.0.1:8000/api/docs
make dev-worker             # Telegram worker (avval: cd backend && ../.venv/bin/python -m app.telegram.auth_cli)
make dev-web                # Panel    → http://127.0.0.1:5173
```

Vite dev-server `/api` so'rovlarini `127.0.0.1:8000`ga uzatadi (boshqa manzil: `VITE_API_PROXY=...`).

## 9. Avtomatik javobni sozlash

**Avtomatik javoblar** bo'limi (Admin va Super Admin):

1. Matnni yozing: markaz nomi, kurslar, narxlar, davomiylik, jadval, manzil, aloqa, sinov darsi, havolalar.
   Tizim o'zidan hech qanday ma'lumot qo'shmaydi — faqat siz yozgan matn yuboriladi.
2. Formatlash tugmalari: **qalin**, *kursiv*, tagiga chizilgan, o'chirilgan, kod, iqtibos, havola.
   O'ng tomonda xabar Telegram'da qanday ko'rinishi va belgilar soni (chegara 4096) ko'rsatiladi.
3. «Yangi mijozlarga avtomatik ma'lumot yuborish»ni yoqing va **Saqlash**ni bosing.

Qoidalar:

- Har bir mijozga xabar **faqat bir marta** yuboriladi. Mijoz Telegram ID orqali aniqlanadi (ism yoki username emas).
- **«Faqat haqiqatan yangi suhbatlarga»** (standart yoqilgan): chatda avval yozishmalar bo'lsa (eski mijoz yoki tizim
  o'rnatilishidan oldingi tanish), xabar yuborilmaydi. Bu tizimni birinchi marta ulaganda hammaga xabar ketishining oldini oladi.
- **Kutish vaqti**: masalan 30 soniya. Shu vaqt ichida operator o'zi javob bersa, avtomatik xabar yuborilmaydi.
- **Istisno ro'yxati**: bu Telegram ID larga avtomatik xabar yuborilmaydi.
- Qayta ulanish, takroriy Telegram hodisasi yoki server qayta ishga tushishi takroriy yuborishga olib kelmaydi.
- Avtomatik xabar **operator javobi hisoblanmaydi**: 5 daqiqalik nazorat davom etadi.

## 10. 5 daqiqalik nazorat (SLA) qanday ishlaydi

1. Mijoz shaxsiy xabar yozadi → tizim suhbatni va xabar metama'lumotini saqlaydi.
2. Agar ochiq murojaat bo'lmasa, yangi **murojaat** ochiladi; muddat = birinchi javobsiz xabar vaqti + 5 daqiqa.
3. Operator Telegram'dan (telefon, kompyuter — qaysi qurilmadan bo'lsa ham) yoki paneldan javob yozadi →
   murojaat yopiladi va javob vaqti hisoblanadi.
4. Muddat o'tsa → murojaat «muddati o'tgan» bo'ladi va rahbarlarga **bitta** ogohlantirish yuboriladi.

Nima javob hisoblanadi va nima hisoblanmaydi:

| Chiquvchi xabar | Javob hisoblanadimi |
|---|---|
| Operatorning oddiy xabari (Telegram yoki panel orqali) | Ha |
| Tizimning avtomatik ma'lumot xabari | Yo'q |
| Avtomatik xabar matnining aynan nusxasi | Yo'q |
| Telegram Business bot yuborgan xabar | Yo'q |
| Uzatilgan (forward) xabar | Standart bo'yicha yo'q (sozlamalarda yoqish mumkin) |
| Xabarni tahrirlash | Yo'q (faqat yangi xabarlar hisoblanadi) |
| Xizmat xabarlari (pin, qo'ng'iroq va h.k.) | Yo'q |

Bir nechta xabar siyosati: mijoz javob kutib yana yozsa, **yangi murojaat ochilmaydi va muddat surilmaydi** — mijoz birinchi
xabaridan beri kutmoqda. Xabarlar soni ko'payadi. Bitta operator javobi butun kutish davrini yopadi.

Boshqa qoidalar:

- Muddat sozlamalarda o'zgartiriladi (1–1440 daqiqa); ochiq murojaatlar muddati darhol qayta hisoblanadi.
- Server qayta ishga tushsa, ochiq murojaatlar yo'qolmaydi va yopilib qolmaydi (hammasi bazada).
  Worker ishlamagan vaqtda kelgan xabarlar ulanishdan keyin qayta o'qiladi (Telethon `catch_up` + suhbatlarni solishtirish).
- Mijoz faqat «rahmat» yozgan bo'lsa, murojaatni panelda **Yopish** mumkin (audit jurnaliga yoziladi).
- Akkaunt kontaktlaridagi odamlar (xodimlar, tanishlar) standart bo'yicha kuzatilmaydi. Istalgan mijozni
  «Monitoringdan chiqarish» mumkin. Operatorning o'zi boshlagan suhbatlar kuzatilmaydi.
- Barcha vaqtlar bazada UTC'da saqlanadi va panelda Toshkent vaqtida (UTC+5) ko'rsatiladi.

## 11. Administratorlarga ogohlantirish

**Sozlamalar → Administratorga ogohlantirish**. Ikki usul:

**A. Ulangan akkaunt orqali** (`userbot`) — eng oddiy. «Chat» maydoniga rahbarlar guruhining `@username`'i yoki
`-100...` ID sini yozing (akkaunt guruh a'zosi bo'lishi kerak). `me` — Saqlangan xabarlar, lekin o'zingizga yozgan
xabaringiz uchun telefon bildirishnoma bermaydi, shuning uchun guruh tavsiya etiladi.

**B. Alohida bot orqali** (`bot`) — har bir administrator telefoniga oddiy bildirishnoma keladi.
1. @BotFather'da bot yarating, tokenni `.env` dagi `ALERT_BOT_TOKEN`ga yozing va `docker compose up -d` qiling.
2. Har bir administrator botga `/start` yozadi.
3. Ularning chat ID larini (masalan, @userinfobot orqali bilib olish mumkin) vergul bilan «Chat ID lar» maydoniga yozing.

**Sinov ogohlantirishini yuborish** tugmasi sozlamani darhol tekshiradi. Ogohlantirishda: mijoz ismi, username, Telegram ID,
murojaat vaqti, javobsiz vaqt, xabarlar soni, (ixtiyoriy) xabar matni va profilga havola bo'ladi.

## 12. Guruhlar va rejalashtirilgan e'lonlar

**Guruhlar** (`Telegram guruhlari`):

1. **Guruhlarni yangilash** — akkaunt a'zo bo'lgan guruh va kanallar ro'yxati Telegram'dan olinadi; har biri uchun
   yozish huquqi tekshiriladi.
2. E'lon yuboriladigan guruhlarni **«E'lonlar uchun»** kalitidan yoqing. Yoqilmagan guruhga tizim hech qachon yozmaydi.
3. Ro'yxatda yo'q guruh: **Qo'lda qo'shish** — `@username`, `https://t.me/username` yoki `-100...` ID.
   Akkaunt avval guruhga a'zo bo'lishi kerak; tizim guruhlarga o'zi qo'shilmaydi, taklif havolalarini qabul qilmaydi.

**E'lonlar** (`Rejalashtirilgan xabarlar → Yangi e'lon`):

1. Sarlavha (faqat panel uchun), asosiy matn va guruhlarni tanlang. Har bir guruh uchun alohida matn yozish mumkin.
2. Jadval: **Bir marta** (vaqt bo'sh = faollashtirilganda darhol), **Har kuni** yoki **Hafta kunlari bo'yicha**
   (Toshkent vaqti, ixtiyoriy boshlanish/tugash sanasi).
3. **Sinov rejimi** — hamma narsa tekshiriladi va tarixga yoziladi, lekin hech narsa yuborilmaydi.
4. **Qoralamani saqlash** → **Jadvalni yoqish** yoki **Hozir yuborish**. Bir nechta guruhga yuborishdan oldin
   tasdiqlash oynasi chiqadi (server ham tasdiqsiz so'rovni rad etadi).
5. Faol e'lonni **To'xtatish / Davom ettirish / Bekor qilish** mumkin; to'xtatilganda navbatdagi guruhlarga ham yuborish to'xtaydi.

Ishonchlilik:

- Rejalar bazada saqlanadi: server qayta ishga tushsa ham bajariladi.
- Har bir guruh bitta yuborishda **ko'pi bilan bir marta** xabar oladi (takroriy yuborish yo'q).
- Guruhlar orasida pauza (standart 5 s); Telegram FloodWait talab qilsa, aynan shuncha kutiladi.
- Vaqtinchalik xato (tarmoq) — kechikish bilan qayta urinish; doimiy xato (huquq yo'q, bloklangan) — qayta urinilmaydi
  va guruh «Yozish huquqi yo'q» deb belgilanadi. Bir guruhdagi xato boshqalariga ta'sir qilmaydi.
- Server `misfire_grace_minutes`dan (standart 60 daqiqa) uzoq o'chiq bo'lsa, o'tib ketgan e'lon kech yuborilmaydi —
  «O'tkazib yuborildi» deb belgilanadi.
- Yuborish vaqtida worker to'satdan to'xtasa, o'sha yuborish «Noma'lum» bo'ladi va avtomatik qayta yuborilmaydi
  (dublikatdan ko'ra Telegram'da tekshirish xavfsizroq).

Har bir guruh bo'yicha natija va xato sabablari **Xabarlar tarixi → Guruh e'lonlari**da.

## 13. Rollar va kirish huquqlari

| Imkoniyat | Operator | Admin | Super Admin |
|---|:-:|:-:|:-:|
| Dashboard, Telegram holati | ✓ | ✓ | ✓ |
| Suhbatlar, javob yozish, murojaatni yopish | o'ziniki + biriktirilmagan¹ | barchasi | barchasi |
| Suhbatni xodimga biriktirish | faqat o'ziga | ✓ | ✓ |
| Mijozni monitoringdan chiqarish | | ✓ | ✓ |
| Avtomatik javob, guruhlar, e'lonlar, tarix, hisobotlar | | ✓ | ✓ |
| Sozlamalar, administratorlar, audit jurnali, qayta ulanish, mijoz ma'lumotini o'chirish | | | ✓ |

¹ Sozlamalardagi «Operatorlar biriktirilmagan suhbatlarni ham ko'radi» bilan boshqariladi.
Barcha tekshiruvlar serverda bajariladi; panelda yashirish faqat qulaylik uchun.

## 14. Testlarni ishga tushirish

Testlar haqiqiy PostgreSQL'da ishlaydi (alohida, bo'sh test bazasi kerak — u har safar migratsiyalar bilan qayta
yaratiladi). Telegram akkaunti yoki internet **kerak emas**: Telegram soxta gateway bilan almashtirilgan.

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://educenter:educenter@localhost:5432/educenter_test
make test           # backend testlari (pytest)
make lint           # ruff lint + format tekshiruvi
make typecheck      # frontend: TypeScript + production build
make check          # hammasi
```

Lokal Python o'rnatmasdan, ishlab turgan Compose stekidagi PostgreSQL bilan:

```bash
source .env
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE educenter_test;"
docker run --rm --network educenter-crm_default -v "$PWD/backend:/src" -w /src \
  -e TEST_DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/educenter_test" \
  python:3.13-slim sh -c 'pip install -q -e ".[dev]" && python -m pytest -q'
```

Test bazasini hech qachon asosiy bazaga yo'naltirmang — testlar uni har safar tozalab qayta yaratadi.

Testlar qamrovi: birinchi murojaatni aniqlash va takroriy avtomatik javobning oldini olish, avtomatik xabar javob
hisoblanmasligi, to'g'ri murojaatni yopish, SLA muddati va takroriy ogohlantirishning oldini olish, qayta ishga
tushishdan keyin tiklanish, e'lonlar holat mashinasi, parallel worker'lar ikki marta yubormasligi, FloodWait va
qayta urinishlar, vaqt mintaqasi va takrorlanish, rollar, CSRF, login bloklash, kiritish validatsiyasi.

## 15. Loglar va muammolarni hal qilish

```bash
docker compose ps                     # servislar holati
docker compose logs -f worker         # Telegram worker loglari
docker compose logs -f api            # API loglari
docker compose logs --since 1h api | grep '"level": "error"'
```

Loglar JSON formatda; har bir API so'rovida `request_id` bor (javob sarlavhasida ham `X-Request-ID`).
Parollar, kodlar, `api_hash`, tokenlar va sessiya ma'lumotlari loglarda avtomatik yashiriladi.

| Belgi | Sabab va yechim |
|---|---|
| «Worker ishga tushmagan» / «Worker javob bermayapti» | `docker compose ps worker`, `docker compose logs worker`. Worker'ni qayta ishga tushiring: `docker compose restart worker`. |
| «Kirish talab qilinadi» | Sessiya yo'q yoki bekor qilingan → 7-bo'lim (`make tg-login`). |
| «Sozlanmagan» | `.env`da `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` yo'q → to'ldiring, `docker compose up -d`. |
| «Kutish rejimi» | Ikkinchi worker ishlayapti; faqat bitta worker bo'lishi kerak. |
| Ogohlantirish kelmayapti | Sozlamalarda chat to'g'riligini tekshiring, «Sinov ogohlantirishini yuborish»ni bosing; xato **Xabarlar tarixi → Ogohlantirishlar**da. |
| E'lon guruhga ketmadi | **Xabarlar tarixi → Guruh e'lonlari**da sababini ko'ring; ko'pincha akkauntda yozish huquqi yo'q yoki guruhda sekin rejim. |
| Panelga kira olmayman (429) | 15 daqiqada 5 marta noto'g'ri parol — 15 daqiqa kuting yoki `reset-password` buyrug'i. |
| Panelga kirib bo'lmaydi, cookie saqlanmaydi | `ENVIRONMENT=production`da panel faqat HTTPS orqali ishlaydi. |

API holati: `GET /api/health` (jarayon) va `GET /api/health/ready` (ma'lumotlar bazasi). Worker holati
dashboard va **Telegram ulanishi** sahifasida; Docker healthcheck worker'ning bazadagi signaliga qaraydi.

## 16. Zaxira nusxa va tiklash

```bash
./scripts/backup.sh                                   # → backups/educenter-YYYYmmdd-HHMMSS.sql.gz (oxirgi 14 tasi saqlanadi)
./scripts/restore.sh backups/educenter-20261012-031500.sql.gz
```

Har kuni avtomatik zaxira (crontab):

```
15 3 * * * cd /opt/educenter-crm && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Zaxiralarni boshqa serverga ham nusxalang. Telegram sessiyasi zaxiraga kiritilmaydi (u maxfiy); server
almashganda 7-bo'limdagi kabi qayta kiring.

## 17. Sessiya va maxfiy ma'lumotlarni himoyalash

- Telegram sessiya fayli — bu akkauntga to'liq kirish huquqi. U faqat `tgsession` volume'ida, `0600` huquq bilan
  saqlanadi, faqat worker konteyneri ko'radi; API va brauzerga hech qachon berilmaydi.
- `.env` faylini `chmod 600` qiling; `.env`, `*.session`, zaxiralar `.gitignore`da.
- Kirish kodi va 2FA paroli hech qayerda saqlanmaydi va loglarga yozilmaydi.
- Shubha tug'ilsa: Telegram → Sozlamalar → Qurilmalar bo'limida «EduCenter CRM» seansini yakunlang va `my.telegram.org`da
  yangi ilova yarating.
- Administrator parollari Argon2id bilan xeshlanadi; sessiyalar server tomonida, cookie `HttpOnly` + `Secure` + `SameSite=Lax`,
  barcha o'zgartiruvchi so'rovlar CSRF token va Origin tekshiruvidan o'tadi; login urinishlari cheklangan.
- Mijoz ma'lumotlari minimal: xabar matnidan faqat qisqa qism (o'chirish mumkin), operator javoblari matni umuman
  saqlanmaydi; eski yozuvlar saqlash muddatidan keyin avtomatik o'chiriladi; mijoz ma'lumotlarini to'liq o'chirish mumkin.

Production tekshiruv ro'yxati: [`docs/SECURITY.md`](docs/SECURITY.md).

## 18. Nima tayyor, nima tashqi sozlash talab qiladi, cheklovlar

**Tayyor va testlangan:** yuqorida tasvirlangan barcha funksiyalar — avtomatik javob, SLA va ogohlantirishlar,
guruh e'lonlari, veb-panelning 13 bo'limi, rollar, audit, saqlash muddati, Docker Compose.

**Tashqi sozlash talab qiladi:** Telegram API kalitlari va bir martalik kirish, HTTPS reverse proxy va domen,
ogohlantirish chati yoki bot, zaxira nusxalar jadvali.

**Ma'lum cheklovlar:**

- Bitta joylashtirish = bitta Telegram akkaunti (sxema ko'p akkauntga kengaytirishga tayyor, lekin hozir yoqilmagan).
- Operator boshqa qurilmadan javob yozsa, kim yozganini Telegram aytmaydi — javob «Operator» deb hisoblanadi.
  Paneldan yozilgan javoblar esa xodim nomi bilan saqlanadi.
- Telegram Business'ning o'z avtomatik javoblari (away/greeting) faqat `via_business_bot` belgisi bo'lsa
  ajratiladi; Telegram buni har doim bildirmasligi mumkin — bunday holatda ularni o'chirib, tizimning avtomatik javobidan foydalaning.
- Shaxsiy chatdagi o'chirilgan xabar uchun Telegram faqat xabar ID sini beradi; operator javobini o'chirish
  yopilgan murojaatni qayta ochmaydi.
- Ish vaqti (masalan, tunda ogohlantirmaslik) hozircha yo'q — kerak bo'lsa SLA'ni o'chirish yoki muddatni oshirish mumkin.
- Matnli xabarlar qo'llab-quvvatlanadi; e'lon va avtomatik javobga rasm/fayl biriktirish yo'q.
- Docker image'lar ushbu muhitda yig'ilmagan (Docker daemon yo'q edi); `compose.yaml` `docker compose config` bilan
  tekshirilgan, backend va frontend esa to'g'ridan-to'g'ri ishga tushirilib testlangan.
