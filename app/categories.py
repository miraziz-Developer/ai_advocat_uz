"""Menu tree: 4 branches of Uzbek law -> situations -> ready-made example questions (one tap = an answer)."""

# (button, situation prompt, example questions). Prompts ask for the facts a lawyer needs; examples are questions the
# bot answers well, so a first-time user sees a good answer before typing anything.
CATEGORIES = [
    ("👨‍👩‍👧 Oila va fuqarolik", [
        ("💍 Ajrashish, aliment",
         "Oila masalalari bo'yicha yordam beraman. Yozing:\n• Masala nima (ajrashish, aliment, bolalar, mol-mulk bo'lish)?\n"
         "• Nikoh FHDYOda qayd etilganmi?\n• Voyaga yetmagan bolalar bormi?",
         ["Erim aliment to'lamayapti, 2 ta bolam bor, nima qilay?", "Ajrashganda uy kimga qoladi?",
          "Aliment necha foiz bo'ladi?"]),
        ("📜 Meros, vasiyatnoma",
         "Meros masalalari bo'yicha yordam beraman. Yozing:\n• Meros qoldiruvchi kim va qachon vafot etgan?\n"
         "• Vasiyatnoma bormi?\n• Merosxo'rlar kimlar va nizo nimada?",
         ["Otam vafot etdi, uy kimga qoladi? 3 aka-ukamiz", "Vasiyatnoma qanday qoldiriladi?",
          "Merosni qabul qilish muddati qancha?"]),
        ("🏠 Uy-joy, ijara",
         "Uy-joy va ijara bo'yicha yordam beraman. Yozing:\n• Siz ijarachimisiz yoki uy egasi?\n• Yozma shartnoma bormi?\n"
         "• Muammo nimada (chiqarib yuborish, depozit, to'lov, ta'mir)?",
         ["Uy egasi muddatidan oldin chiqib ket deyapti, shartnoma bor", "Ijaraga bergan uyimga pul to'lashmayapti",
          "Depozitni qaytarishmayapti"]),
        ("🤝 Qarz, shartnoma",
         "Qarz va shartnomalar bo'yicha yordam beraman. Yozing:\n• Qarz yoki shartnoma summasi va muddati?\n"
         "• Yozma tilxat yoki shartnoma bormi?\n• Hozir nima bo'lyapti?",
         ["Do'stimga qarz berdim, qaytarmayapti, tilxat bor", "Kredit to'lay olmayapman, bank sudga beraman deyapti",
          "Shartnomani bir tomonlama bekor qilsa bo'ladimi?"]),
        ("🛒 Iste'molchi huquqlari",
         "Iste'molchi huquqlari bo'yicha yordam beraman. Yozing:\n• Nima sotib oldingiz / qanday xizmat?\n"
         "• Muammo nimada (sifatsiz, qaytarib olishmayapti, kafolat)?\n• Chek yoki shartnoma bormi?",
         ["Do'kondan telefon oldim, 3 kunda buzildi, qaytarib olishmayapti",
          "Sifatli kiyimni qaytarsa bo'ladimi?", "Kafolatdagi tovarni tuzatib berishmayapti"]),
    ]),
    ("👷 Mehnat va ijtimoiy", [
        ("💰 Ish haqi",
         "Ish haqi bo'yicha yordam beraman. Yozing:\n• Necha oy va qancha summa to'lanmagan?\n"
         "• Rasmiy mehnat shartnomasi bormi?\n• Hozir ham shu yerda ishlayapsizmi?",
         ["Oyligimni 3 oydan beri bermayapti, nima qilay?", "Oylik kechiksa kompensatsiya bormi?",
          "Ishdan ketganimda hisob-kitob qilishmadi"]),
        ("🚪 Ishdan bo'shatish",
         "Ishdan bo'shatish bo'yicha yordam beraman. Yozing:\n• Qachon va qanday asosda bo'shatildingiz?\n"
         "• Buyruq berildimi, ogohlantirishdimi?\n• Ishga tiklanmoqchimisiz yoki kompensatsiya olmoqchimisiz?",
         ["Meni ogohlantirmasdan ishdan bo'shatishdi", "Homiladorligimda ishdan bo'shatishsa bo'ladimi?",
          "Shtat qisqarganda qancha kompensatsiya to'lanadi?"]),
        ("📄 Mehnat shartnomasi, ta'til",
         "Mehnat shartnomasi va ta'til bo'yicha yordam beraman. Yozing:\n• Savolingiz nimaga oid (shartnoma, ta'til, "
         "ish vaqti, sinov muddati)?\n• Qayerda va qancha vaqtdan beri ishlaysiz?",
         ["Yillik ta'til necha kun bo'ladi?", "Sinov muddati qancha bo'lishi mumkin?",
          "Ish beruvchi mehnat shartnomasi tuzmayapti"]),
        ("👴 Pensiya, nafaqa",
         "Pensiya va nafaqalar bo'yicha yordam beraman. Yozing:\n• Qanday pensiya yoki nafaqa (yosh, nogironlik, "
         "boquvchisini yo'qotganlik, bola parvarishi)?\n• Yoshingiz va ish stajingiz?",
         ["Pensiyaga necha yoshda chiqiladi?", "Bola parvarishi nafaqasi qancha?", "Nogironlik pensiyasini qanday olaman?"]),
    ]),
    ("🚔 Jarima va jinoyat", [
        ("🚗 Jarima, YHXX",
         "Jarima va yo'l harakati bo'yicha yordam beraman. Yozing:\n• Qanday jarima yoki qoidabuzarlik?\n"
         "• Qachon va qanday rasmiylashtirildi (kamera, inspektor)?\n• Rozimisiz yoki shikoyat qilmoqchimisiz?",
         ["Qizil chiroqdan o'tib ketdim, jarima qancha?", "Tezlik uchun kamera jarima yozdi, mashinani men haydamagandim",
          "Haydovchilik guvohnomasiz haydasam nima bo'ladi?"]),
        ("⚖️ Jinoyat ishi, tergov",
         "Jinoyat ishi bo'yicha yordam beraman. Yozing:\n• Siz jabrlanuvchimisiz, guvohmi yoki gumon qilinuvchi?\n"
         "• Nima sodir bo'ldi va qachon?\n• Tergovchi chaqirdimi?\n\nMuhim: jinoyat ishida albatta advokat oling.",
         ["Meni o'g'irlikda nohaq ayblashyapti", "Telefonimni o'g'irlashdi, qayerga murojaat qilaman?",
          "Tergovchi chaqirdi, advokatsiz borsam bo'ladimi?"]),
        ("🔊 Qo'shni, shovqin, bezorilik",
         "Qo'shnilar va jamoat tartibi bo'yicha yordam beraman. Yozing:\n• Muammo nimada (shovqin, janjal, haqorat, "
         "zarar)?\n• Qachondan beri davom etyapti?\n• Dalil (video, guvoh) bormi?",
         ["Qo'shnim tunda baland musiqa qo'yadi", "Qo'shnim meni haqorat qildi", "Mayda bezorilik uchun qancha jarima?"]),
        ("🏦 MIB, majburiy ijro",
         "MIB va majburiy ijro bo'yicha yordam beraman. Yozing:\n• Qarz nima uchun va qancha?\n"
         "• MIB qanday cheklov qo'ydi (chet elga chiqish, mashina, hisob raqam)?\n• Qarzni bo'lib to'lay olasizmi?",
         ["MIB chet elga chiqishga taqiq qo'ydi, qanday chiqaman?", "Qarzni bo'lib to'lasam bo'ladimi?",
          "MIB kartamdagi pulni yechib oldi"]),
    ]),
    ("🏛 Davlat va biznes", [
        ("📨 Davlat idoralariga murojaat",
         "Davlat idoralariga murojaat bo'yicha yordam beraman. Yozing:\n• Qaysi idoraga va nima masalada?\n"
         "• Avval murojaat qilganmisiz, javob berishdimi?",
         ["Hokimiyat murojaatimga javob bermayapti", "Murojaat necha kunda ko'rib chiqilishi kerak?",
          "Mansabdor shaxs ustidan qayerga shikoyat qilaman?"]),
        ("💼 Soliq, YaTT, biznes",
         "Soliq va tadbirkorlik bo'yicha yordam beraman. Yozing:\n• Siz YaTT, o'zini o'zi band qilgan yoki MChJ'misiz?\n"
         "• Savol nimaga oid (soliq, ro'yxatdan o'tish, tekshiruv, jarima)?",
         ["O'zini o'zi band qilgan shaxs qanday soliq to'laydi?", "YaTT qanday ochiladi?",
          "Soliq tekshiruvi kelsa nima qilay?"]),
        ("🪪 Pasport, propiska",
         "Pasport va ro'yxatga olish bo'yicha yordam beraman. Yozing:\n• Savol nimaga oid (pasport, ID-karta, doimiy "
         "yoki vaqtincha propiska)?\n• Qaysi shaharda?",
         ["Pasportimni yo'qotib qo'ydim, jarima bormi?", "Toshkentga propiska qanday qilinadi?",
          "Vaqtincha ro'yxatga turish uchun nima kerak?"]),
        ("🎓 Ta'lim, kontrakt",
         "Ta'lim bo'yicha yordam beraman. Yozing:\n• Maktab, kollej yoki oliy ta'limmi?\n"
         "• Muammo nimada (kontrakt, o'qishdan chiqarish, ko'chirish)?",
         ["Kontraktni bo'lib to'lasam bo'ladimi?", "O'qishdan chetlashtirishdi, nima qilay?",
          "Boshqa universitetga ko'chish mumkinmi?"]),
    ]),
]

# Buttons of the previous keyboard: people who have not pressed /start since still see them.
OLD_BUTTONS = {"👷 Mehnat": (1, 0), "🏠 Uy-joy, ijara": (0, 2), "👨‍👩‍👧 Oila, ajrashish": (0, 0),
               "🚗 Jarima, YHXX": (2, 0), "🛒 Iste'molchi": (0, 4), "📜 Meros": (0, 1)}
