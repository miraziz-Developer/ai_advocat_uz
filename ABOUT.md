

# ⚖️ AI Huquqiy Yordamchi — loyiha haqida to'liq ma'lumot

**Telegram:** [@yurist_aiuz_bot](https://t.me/yurist_aiuz_bot) · **Kod:** [github.com/miraziz-Developer/ai_advocat_uz](https://github.com/miraziz-Developer/ai_advocat_uz) · **Server:** `https://ai-advocat-uz.onrender.com`

O'zbekiston qonunchiligi bo'yicha AI yordamchi. Bot oddiy odam tilida yozilgan yoki ovozda aytilgan vaziyatni
tushunadi, unga qaysi qonun taalluqli ekanini aniqlaydi va advokatdek javob beradi: modda raqami, aniq jazo yoki
jarima miqdori, nima qilish kerakligi va qanday dalil yig'ish kerakligi bilan.

---

## 1. Asosiy g'oya

Oddiy AI (ChatGPT va boshqalar) O'zbekiston qonunlarini xotiradan "eslaydi" va ko'pincha **adashadi**: modda
raqamini, jarima miqdorini, muddatni o'zidan to'qiydi. Bu loyihada AI hech narsani xotiradan aytmaydi:

1. Barcha amaldagi qonunlar **lex.uz**'dan (Adliya vazirligining rasmiy milliy bazasi) yuklab olingan va bazada saqlanadi.
2. Har bir savolda bot avval kerakli qonun moddalarini bazadan topadi.
3. AI **faqat shu moddalar asosida** javob yozadi va har bir fikrga manba (`[1]`) qo'yadi.
4. Javob oxirida lex.uz havolalari chiqadi va ular aynan kerakli moddaga olib boradi.
5. Mos modda topilmasa, AI "bazada topilmadi" deb ochiq aytadi.

Bu yondashuv **RAG** (Retrieval-Augmented Generation) deb ataladi. Modelni "o'qitish" (fine-tuning) bilan
solishtirganda u aniqroq, arzonroq ishlaydi va qonun o'zgarsa ham darhol yangilanadi.

---

## 2. Imkoniyatlar

| Funksiya | Tavsif | Narx |
|---|---|---|
| 💬 **Huquqiy savol-javob** | Vaziyatni yozing, bot huquqiy baho, modda, jazo yoki jarima va qadamlarni aytadi | Bepul |
| 🎙 **Ovozli xabar** | O'zbekcha yoki ruscha gapiring, bot matnga aylantiradi ("Siz dedingiz: ...") va javob beradi. 10 daqiqagacha | Bepul |
| 📄 **Hujjat tahlili** | Shartnoma yoki hujjatni rasm, albom (10 sahifagacha), PDF yoki Word ko'rinishida yuboring. Bot asosiy shartlarni, xavfli bandlarni va tavsiyalarni beradi | Bepul |
| 🔘 **Vaziyat tugmalari** | Mehnat, Uy-joy/ijara, Oila/ajrashish, Jarima/YHXX, Iste'molchi, Meros | Bepul |
| 📝 **Hujjat tayyorlash** | Ariza, shikoyat, da'vo arizasi, talabnoma: qonun moddalariga havolalar bilan Word (.docx) faylda | **Pullik** (15 000 so'm) |
| 👍👎 **Baholash** | Har bir javob ostida chiqadi. Yomon javoblar admin uchun saqlanadi | — |

**Pul topish modeli:** maslahat va tahlil bepul, foydalanuvchilarni jalb qiladi. Hujjatni tayyor holda olish
pullik, chunki odamlar advokatga bunga 200–500 ming so'm to'laydi. AI suhbat davomida hujjat kerakligini o'zi
sezadi va "📝 Hujjatni tayyorlab berish" tugmasini taklif qiladi.

### Javob formati (misol)
```
⚖️ Huquqiy baho
Bu — Jinoyat kodeksining 109-moddasi: qasddan badanga yengil shikast yetkazish.

📌 Qonun nima deydi
• BHMning 25–50 baravari jarima [1]
• Yoki 2 yilgacha axloq tuzatish ishlari, yoki 1 yilgacha ozodlikdan mahrum qilish [1]

✅ Nima qilish kerak
1. Darhol sud-tibbiy ekspertizasidan o'ting.
2. IIBga ariza bering, guvohlarni ko'rsating.

⚠️ Diqqat
Kechiksangiz, jarohatni isbotlash qiyinlashadi.

📚 Manbalar (lex.uz)
[1] Jinoyat kodeksi, 109-modda  ← bosiladigan havola
```

---

## 3. Qonunlar bazasi

- **594 ta hujjat, ~25 600 bo'lak.** Bu lex.uz'dagi barcha amaldagi qonunlar va kodekslar: Konstitutsiya,
  Fuqarolik, Mehnat, Jinoyat, Ma'muriy javobgarlik, Oila, Uy-joy, Soliq, Yer, Bojxona, protsessual kodekslar,
  shuningdek iste'molchi, yo'l harakati, notariat, advokatura, pensiya, ipoteka, ta'lim, shovqin, rieltorlik
  va boshqa qonunlar.
- O'zgartirish kirituvchi qonunlar alohida yuklanmaydi, chunki lex.uz ularni asosiy qonun matniga allaqachon kiritgan.
- Matn kirill yozuvidan lotinga avtomatik o'giriladi.
- **Har kuni soat 12:30 da** (Toshkent) GitHub Actions lex.uz'ni tekshiradi: yangi qonunlarni qo'shadi, o'zgarganlarini yangilaydi.
- Ma'no-qidiruv (embedding) bepul kvota bilan kuniga taxminan 1000 bo'lakdan to'ldirilib boradi.

---

## 4. Bot qonunni qanday topadi (3 qatlam)

```
Foydalanuvchi: "Qo'shnim tunda baland musiqa qo'yadi"
        │
        ├─ 1. 🧠 AI advokat — 543 ta qonun ro'yxatini ko'rib, taalluqlilarini tanlaydi
        ├─ 2. 📋 Vaziyatlar xaritasi — 22 ta kundalik mavzu (AI'siz, har doim ishlaydi)
        └─ 3. 🔤 Qonun nomi bo'yicha moslik — "shovqin" so'zi → Shovqin to'g'risidagi qonun
        │
        ▼
Qidiruv: tanlangan har bir qonundan eng mos 3 ta modda va umumiy qidiruv natijalari (8 ta manba)
        │
        ▼
AI javobi: faqat shu manbalar asosida → Shovqin qonuni 13-modda va MJtK 192-modda
```

- **Kalit so'z qidiruvi** o'zbek tilining qo'shimchalarini tushunadi (bolam → bola, alimentni → aliment) va
  modda sarlavhasiga ustunlik beradi.
- **Ma'no-qidiruv** (vektor) barcha bo'laklar embedding qilinganidan keyin avtomatik yoqiladi.
- Bepul AI band bo'lsa, bot uni 5 daqiqa kutmaydi va 2- hamda 3-qatlam bilan ishlaydi.

---

## 5. To'lov tizimi

1. Foydalanuvchi "📝 Hujjat tayyorlatish" yoki "💳 Balans" tugmasini bosadi.
2. Bot karta raqami va qabul qiluvchi ismini ko'rsatadi.
3. Foydalanuvchi Click, Payme, Uzum yoki bank ilovasi orqali pul o'tkazib, chek skrinshotini yuboradi.
4. **AI chekni o'qiydi** (summa, qabul qiluvchi karta yoki ism, sana, holat, tahrir belgilari), **kod esa qaror qiladi**:
   - summa kam, qabul qiluvchi boshqa, chek 48 soatdan eski, to'lov muvaffaqiyatsiz, rasm chekka o'xshamasa → rad etiladi;
   - bir chekni (rasm yoki tranzaksiya raqami) ikki marta ishlatib bo'lmaydi.
5. Tasdiqlangan har bir to'lov **adminga** "❌ Soxta — bekor qilish" tugmasi bilan keladi.

⚠️ Yaxshi tahrirlangan soxta chekni AI 100% aniqlay olmaydi. Tushumlarni bank ilovasida solishtirib turing.
Daromad o'sganda Click yoki Payme merchant API'ga o'tish kerak (YaTT yoki MChJ talab qilinadi).

---

## 6. Texnologiyalar

| Qism | Texnologiya | Narx |
|---|---|---|
| Bot | Python 3.12, aiogram 3 (Telegram), webhook | — |
| AI | Google Gemini API: 3.x flash/flash-lite modellari (avtomatik zaxira bilan), gemini-embedding-001 | Bepul tarif |
| Baza | PostgreSQL + pgvector, **Neon** (Ohio, AWS us-east-2) | Bepul (0,5 GB; hozir ~105 MB) |
| Server | **Render** free web service (Ohio), o'zini ping qilib uyg'oq turadi | Bepul |
| Qonunlarni yangilash | GitHub Actions, har kuni | Bepul |
| Hujjatlar | python-docx (Word) | — |

**Ishonchlilik choralari:**
- Model band (503) yoki limit tugagan (429) bo'lsa, bot keyingi modelga o'tadi. Har bir modelga ko'pi bilan 25 soniya beriladi.
- Baza ulanishi uzilsa, so'rov qayta yuboriladi.
- Suhbat holati ("chek kutilmoqda") bazada saqlanadi va server qayta ishga tushsa ham yo'qolmaydi.
- Xato bo'lsa, adminga Telegram'da ogohlantirish keladi (10 daqiqada ko'pi bilan 1 ta).
- Har bir foydalanuvchi uchun kunlik bepul limit bor (`FREE_DAILY_LIMIT`, standart 25).

---

## 7. Fayllar tuzilishi

```
app/
  main.py      — ishga tushirish: Render'da webhook, lokalda polling; bot profili
  bot.py       — Telegram handlerlari: menyu, savol, ovoz, fayl/albom, to'lov, admin
  rag.py       — "miya": qonun tanlash, qidiruv, javob/tahlil/hujjat promptlari
  db.py        — PostgreSQL: qonunlar, qidiruv, foydalanuvchilar, to'lovlar, baholar
  llm.py       — Gemini: model zaxirasi, embedding, JSON javoblar
  lexuz.py     — lex.uz: qonunlar ro'yxati, sahifani moddalarga bo'lish
  ingest.py    — qonunlarni bazaga yuklash (python -m app.ingest --all)
  payments.py  — chekni tekshirish qoidalari
  translit.py  — kirill → lotin
data/sources.txt — majburiy kodekslar ro'yxati
tests/           — 21 ta avtomatik test
render.yaml      — Render sozlamasi
.github/workflows/update-laws.yml — kunlik qonun yangilash
```

---

## 8. Admin buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/stats` | Foydalanuvchilar, qonunlar, to'lovlar, 👍/👎 soni, joriy versiya |
| `/bad` | 👎 bosilgan oxirgi javoblar (savol va javob bilan) |
| `/credit <user_id> <soni>` | Kredit qo'shish yoki ayirish (manfiy son bilan ayiriladi) |

Adminga avtomatik keladigan xabarlar: tasdiqlangan to'lovlar (bekor qilish tugmasi bilan), botdagi xatolar, 👎 baholar.

---

## 9. Sozlamalar (Render → Environment)

| O'zgaruvchi | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather tokeni |
| `GEMINI_API_KEY` | aistudio.google.com kaliti |
| `DATABASE_URL` | Neon ulanish manzili |
| `ADMIN_IDS` | Admin Telegram ID (vergul bilan bir nechta) |
| `CARD_NUMBER`, `CARD_HOLDER` | To'lov qabul qilinadigan karta va egasining ismi |
| `DOC_PRICE` | 1 ta hujjat narxi (standart 15000) |
| `FREE_DAILY_LIMIT` | Kunlik bepul so'rovlar soni (standart 25) |
| `WEBHOOK_SECRET` | Webhook himoyasi (avtomatik yaratiladi) |
| `CHAT_MODELS`, `ROUTER_MODELS`, `LITE_MODELS` | Ixtiyoriy: Gemini modellari tartibi |

GitHub Secrets (kunlik yangilash uchun): `DATABASE_URL`, `GEMINI_API_KEY`.

---

## 10. Ishga tushirish

**Lokal:**
```bash
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env              # qiymatlarni to'ldiring
.venv/bin/python -m app.ingest --all   # qonunlarni yuklash (~8 daqiqa)
.venv/bin/python -m app.main           # bot (polling)
.venv/bin/python -m pytest -q          # testlar
```

**Render:** GitHub'ga push qiling → Render → Manual Deploy (yoki Auto-Deploy) → `/stats` da versiyani tekshiring.

---

## 11. Cheklovlar (ochiq aytilgan)

1. **Gemini bepul tarifi:** flash modellarida kuniga 20 tadan so'rov bor, modellar tez-tez band bo'ladi.
   Javob 20–60 soniyada keladi. Minglab foydalanuvchi uchun **billing yoqish kerak** (kod o'zgarmaydi).
2. **Ma'no-qidiruv** taxminan 3–4 haftada to'liq bo'ladi (kuniga ~1000 bo'lak). Ungacha kalit so'z qidiruvi va AI tanlovi ishlaydi.
3. **Soxta chek** AI tomonidan 100% aniqlanmaydi, shuning uchun admin nazorati kerak.
4. Bot **litsenziyali advokat emas**. Har bir javobda ogohlantirish bor, jiddiy ishlarda advokatga murojaat qilish tavsiya etiladi.
5. Gemini bepul tarifida yuborilgan ma'lumotlardan Google modelni yaxshilash uchun foydalanishi mumkin.

---

## 12. Keyingi qadamlar

| Qadam | Nima beradi | Kim qiladi |
|---|---|---|
| Gemini billing | 5–10 soniyalik javob, cheksiz foydalanuvchi, ma'no-qidiruv 10 daqiqada to'ladi | Siz (AI Studio) |
| YaTT + Click/Payme merchant | To'lovni 100% avtomatik tasdiqlash | Siz |
| Bot token va API kalitni yangilash | Xavfsizlik (ular chatda ochiq yozilgan edi) | Siz |
| 👎 javoblarni tahlil qilish | Sifatni oshirish | `/bad` → tuzatish |
| Litsenziyali advokatlarga ulash | Qo'shimcha daromad (komissiya) | Keyinroq |
| Web versiya / Telegram Mini App | Kengroq auditoriya | Keyinroq |
