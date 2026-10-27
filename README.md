# AI Huquqiy Yordamchi (Telegram bot)

O'zbekiston qonunchiligi bo'yicha AI yordamchi. Javoblar **faqat lex.uz rasmiy matnlariga** asoslanadi va har bir
modda havola bilan ko'rsatiladi. Bazada mos modda topilmasa, AI buni ochiq aytadi va o'zidan to'qib chiqarmaydi.

## Nima qila oladi
| Funksiya | Narx |
|---|---|
| Huquqiy savol-javob, vaziyat tugmalari (Mehnat, Uy-joy, Oila, Jarima, Iste'molchi, Meros) | bepul |
| Shartnoma yoki hujjatni rasm / albom (10 sahifagacha) / PDF / Word orqali tahlil qilish | bepul |
| Ovozli xabar (o'zbek / rus): matnga aylantirib, savolga javob beradi | bepul |
| Ariza, shikoyat, da'vo arizasi, talabnoma tayyorlash (Word fayl) | pullik (`DOC_PRICE`) |

AI suhbat davomida hujjat kerakligini o'zi aniqlaydi va "📝 Hujjatni tayyorlab berish" tugmasini taklif qiladi.
To'lov kartaga o'tkazma orqali qilinadi. Foydalanuvchi chek skrinshotini yuboradi, AI chekdagi summa, qabul
qiluvchi karta/ism, sana, holat va tahrir belgilarini o'qiydi, keyin kod qoidalar asosida qaror qiladi.
Bir chekni ikki marta ishlatib bo'lmaydi. Har bir tasdiqlangan to'lov adminga
"❌ Soxta — bekor qilish" tugmasi bilan yuboriladi.

## Arxitektura
```
lex.uz ──(app/ingest.py)──► moddalarga bo'lish ► Gemini embedding ► Postgres + pgvector
Telegram ► Render (app/main.py, webhook) ► app/bot.py ► app/rag.py:
      savol → qidiruv so'rovi → gibrid qidiruv (vektor + matn) → 8 ta modda → Gemini javobi + [manba] havolalari
```
* `app/lexuz.py`: lex.uz sahifasini moddalarga ajratadi va kirillni lotinga o'giradi.
* `app/payments.py`: chekni tekshirish qoidalari.
* `data/sources.txt`: bazaga yuklanadigan qonunlar ro'yxati.

## Sizdan kerak bo'ladigan narsalar
1. **Telegram bot tokeni**: [@BotFather](https://t.me/BotFather) → `/newbot` → `BOT_TOKEN`.
2. **Gemini API kaliti**: <https://aistudio.google.com/apikey> → `GEMINI_API_KEY`.
3. **Baza**: [supabase.com](https://supabase.com) → New project → Connect → **Session pooler** connection string →
   `DATABASE_URL`. To'g'ridan-to'g'ri ulanish faqat IPv6 orqali ishlaydi, Render esa unga ulana olmaydi.
   Shuning uchun aynan pooler kerak. `pgvector` kengaytmasi avtomatik yoqiladi.
4. **Admin ID**: [@userinfobot](https://t.me/userinfobot) sizning raqamli ID'ingizni beradi → `ADMIN_IDS`.
5. **Karta**: `CARD_NUMBER` va `CARD_HOLDER` (karta egasining ismi, chekda qanday ko'rinsa shunday).

## Lokal ishga tushirish
```bash
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
```
```bash
cp .env.example .env
```
`.env` faylini to'ldiring, keyin qonunlarni bazaga yuklang. Bu bir marta qilinadi, taxminan 20–40 daqiqa ketadi
(~6800 bo'lak):
```bash
.venv/bin/python -m app.ingest
```
Botni ishga tushirish (lokalda long polling rejimida ishlaydi):
```bash
.venv/bin/python -m app.main
```
Testlar:
```bash
.venv/bin/python -m pytest -q
```

## Render'ga deploy
1. Kodni GitHub'ga yuklang.
2. Render → New → **Blueprint** → repo'ni tanlang. `render.yaml` hamma narsani sozlaydi.
   Keyin maxfiy qiymatlarni kiriting (`BOT_TOKEN`, `DATABASE_URL`, `GEMINI_API_KEY`, `ADMIN_IDS`, `CARD_*`).
3. Bot ishga tushganda webhook o'zi o'rnatiladi (`RENDER_EXTERNAL_URL` orqali).
4. **Uxlab qolmaslik:** bot har 10 daqiqada o'zining `/health` manziliga so'rov yuboradi. Zaxira sifatida
   [cron-job.org](https://cron-job.org) yoki UptimeRobot'da `https://<sizning-servis>.onrender.com/health`
   manziliga har 10 daqiqada ping qo'ying. Bitta servis 24/7 ishlashi bepul 750 soat/oy limitiga sig'adi.

## Qonunlarni yangilab turish
`.github/workflows/update-laws.yml` har kuni lex.uz.ni tekshiradi va o'zgargan qonunlarni qayta yuklaydi.
GitHub repo → Settings → Secrets → `DATABASE_URL`, `GEMINI_API_KEY` qo'shing.

Yangi qonun qo'shish uchun uni lex.uz'da **o'zbekcha** oching, URL'dagi raqamni `data/sources.txt` fayliga
qo'shing va `python -m app.ingest` buyrug'ini ishga tushiring. Ruscha versiyaning raqami boshqacha bo'ladi.

## Admin buyruqlari
* `/stats`: foydalanuvchilar, bazadagi qonunlar va to'lovlar soni.
* `/credit <user_id> <soni>`: kredit qo'shish yoki ayirish (manfiy son bilan ayiriladi).
* `/bad`: foydalanuvchilar 👎 bergan oxirgi javoblar (savol va javob bilan).
* Botda xato bo'lsa yoki 👎 bosilsa, adminga avtomatik xabar keladi (10 daqiqada ko'pi bilan 1 ta).

## Bilish kerak bo'lgan cheklovlar
* **Chekni AI 100% tasdiqlay olmaydi.** Yaxshi tahrirlangan soxta skrinshot o'tib ketishi mumkin. Shuning uchun
  tushumlarni bank ilovasida solishtirib turing va soxtasini adminga kelgan tugma bilan bekor qiling.
  Daromad o'sganda Click/Payme merchant API'ga o'tish kerak: unda to'lovni server o'zi tasdiqlaydi.
* Bepul Gemini tarifida yuborilgan ma'lumotlar Google tomonidan modelni yaxshilash uchun ishlatilishi mumkin.
  Limit tugasa yoki foydalanuvchilar ko'paysa, AI Studio'da billing yoqing.
* Bazada 15 ta kodeks va 8 ta muhim qonun bor (Konstitutsiya, Fuqarolik, Mehnat, Jinoyat, MJtK, Oila, Uy-joy,
  Soliq, protsessual kodekslar, Yer, Bojxona; iste'molchi, yo'l harakati, murojaatlar, shaxsiy ma'lumot, bandlik,
  sud qarorlarini ijro etish, xotin-qizlar himoyasi, ta'lim). Yangilari `data/sources.txt` orqali qo'shiladi.
* Bepul Gemini tarifida embedding kuniga taxminan 1000 ta so'rov bilan cheklangan. Barcha kodekslarni boshlang'ich
  yuklash shu sababli taxminan bir hafta davom etadi, buni kunlik GitHub Actions o'zi bajaradi. Limit tugaganda
  bot kalit so'z bo'yicha qidiruvga o'tadi va ishlashda davom etadi. Billing yoqilsa, hammasi 10 daqiqada yuklanadi.
