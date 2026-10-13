// Russian translations — filled by the i18n conversion. Key = Uzbek source string.
export const ru: Record<string, string> = {
  // Incidents.tsx
  "Telegramda javob": "Ответ в Telegram",
  "Panel orqali javob": "Ответ через панель",
  "Qo'lda yopilgan": "Закрыто вручную",
  "Murojaat yopildi": "Обращение закрыто",
  "Javobsiz murojaatlar": "Неотвеченные обращения",
  "Mijoz yozgan, lekin operator hali javob bermagan suhbatlar. Avtomatik javob hisobga olinmaydi.":
    "Переписки, где клиент написал, но оператор ещё не ответил. Автоматический ответ не учитывается.",
  "Holat bo'yicha filtr": "Фильтр по статусу",
  "Kutmoqda": "Ожидает",
  "Muddati o'tgan": "Просрочено",
  "Muddat buzilgan (barchasi)": "Срок нарушен (все)",
  "Javob berilgan": "Отвечено",
  "Yopilgan": "Закрыто",
  "Javob kutayotgan mijoz yo'q": "Нет клиентов, ожидающих ответа",
  "Bu bo'limda yozuv yo'q": "В этом разделе нет записей",
  "Yangi murojaat kelganda shu yerda paydo bo'ladi.": "Новое обращение появится здесь.",
  "Mijoz": "Клиент",
  "Birinchi xabar": "Первое сообщение",
  "Murojaat vaqti": "Время обращения",
  "Kutish": "Ожидание",
  "Javob vaqti": "Время ответа",
  "Ogohlantirish": "Оповещение",
  "Amallar": "Действия",
  "{n} ta xabar": "{n} сообщений",
  "Ochish": "Открыть",
  "Yopish": "Закрыть",
  "Murojaatni javobsiz yopish": "Закрыть обращение без ответа",
  "murojaati javob talab qilmaydi deb belgilanadi (masalan, mijoz faqat «rahmat» yozgan). Ogohlantirish yuborilmaydi. Bu amal audit jurnaliga yoziladi.":
    "— обращение будет отмечено как не требующее ответа (например, клиент написал только «спасибо»). Оповещение не отправляется. Это действие записывается в журнал аудита.",

  // Settings.tsx
  "Forma tayyor emas": "Форма не готова",
  "Sozlamalar saqlandi": "Настройки сохранены",
  "Sinov ogohlantirishi yuborildi — chatni tekshiring": "Тестовое оповещение отправлено — проверьте чат",
  "Yuborilmadi": "Не отправлено",
  "Sozlamalar": "Настройки",
  "Javob nazorati, ogohlantirishlar, maxfiylik va e'lonlar bo'yicha tizim qoidalari.":
    "Системные правила по контролю ответов, оповещениям, конфиденциальности и объявлениям.",
  "Saqlash": "Сохранить",
  "Javob nazorati (SLA)": "Контроль ответов (SLA)",
  "Javobsiz murojaatlarni kuzatish": "Отслеживать неотвеченные обращения",
  "Javob berish muddati (daqiqa)": "Срок ответа (минут)",
  "Shu vaqt ichida operator javob bermasa, murojaat «muddati o'tgan» bo'ladi. Ochiq murojaatlar muddati darhol qayta hisoblanadi.":
    "Если оператор не ответит в течение этого времени, обращение станет «просроченным». Сроки открытых обращений немедленно пересчитываются.",
  "Uzatilgan (forward) xabarni javob deb hisoblash": "Считать пересланное (forward) сообщение ответом",
  "O'chiq bo'lsa, operator boshqa chatdan xabar uzatsa, murojaat ochiq qoladi.":
    "Если выключено, при пересылке оператором сообщения из другого чата обращение остаётся открытым.",
  "Administratorga ogohlantirish": "Оповещение администратора",
  "Ogohlantirish yuborish": "Отправлять оповещения",
  "Qanday yuborilsin": "Как отправлять",
  "Ulangan akkaunt orqali (guruh yoki chatga)": "Через подключённый аккаунт (в группу или чат)",
  "Alohida bot orqali (ALERT_BOT_TOKEN)": "Через отдельный бот (ALERT_BOT_TOKEN)",
  "Chat ID lar": "ID чатов",
  "Chat": "Чат",
  "Botga /start yozgan administratorlarning chat ID lari, vergul bilan.":
    "ID чатов администраторов, написавших боту /start, через запятую.",
  "Rahbarlar guruhi: @username yoki -100… ID. «me» — Saqlangan xabarlar (bildirishnoma kelmaydi).":
    "Группа руководителей: @username или ID -100… «me» — Сохранённые сообщения (уведомления не приходят).",
  "@rahbarlar_guruhi": "@gruppa_rukovoditeley",
  "Ogohlantirishda xabar matnini ko'rsatish": "Показывать текст сообщения в оповещении",
  "Sinov ogohlantirishini yuborish": "Отправить тестовое оповещение",
  "Avval saqlang": "Сначала сохраните",
  "Monitoring doirasi": "Область мониторинга",
  "Telefon kontaktlaridagi odamlarni kuzatmaslik": "Не отслеживать людей из контактов телефона",
  "Akkaunt kontaktlarida saqlangan shaxslar (xodimlar, tanishlar) bilan suhbatlar biznes murojaati hisoblanmaydi.":
    "Переписки с лицами, сохранёнными в контактах аккаунта (сотрудники, знакомые), не считаются бизнес-обращениями.",
  "Kuzatilmaydigan Telegram ID lar": "Не отслеживаемые Telegram ID",
  "Faqat musbat raqamli ID lar": "Только положительные числовые ID",
  "Bu foydalanuvchilarning xabarlari umuman saqlanmaydi.": "Сообщения этих пользователей не сохраняются вообще.",
  "Operatorlar biriktirilmagan suhbatlarni ham ko'radi": "Операторы видят также непривязанные переписки",
  "Maxfiylik va saqlash muddati": "Конфиденциальность и срок хранения",
  "Mijoz xabari matnining qisqa qismini saqlash": "Сохранять фрагмент текста сообщения клиента",
  "O'chirilsa, mavjud matnlar ham keyingi tozalashda o'chiriladi.":
    "Если выключено, существующие тексты также удаляются при следующей очистке.",
  "Operator javobi matnini saqlash": "Сохранять текст ответа оператора",
  "Yoqilsa, operator yozgan javoblar matni (panel va Telegram orqali) suhbatlarda ko'rinadi. O'chirilsa, mavjud matnlar ham keyingi tozalashda o'chiriladi.":
    "Если включено, текст ответов оператора (через панель и Telegram) отображается в переписках. Если выключено, существующие тексты также удаляются при следующей очистке.",
  "Saqlanadigan belgilar soni": "Количество сохраняемых символов",
  "Xabarlarni saqlash muddati (kun)": "Срок хранения сообщений (дней)",
  "Eskiroq xabar yozuvlari har soatda avtomatik o'chiriladi.":
    "Более старые записи сообщений автоматически удаляются каждый час.",
  "E'lonlar": "Объявления",
  "Guruhlar orasidagi pauza (soniya)": "Пауза между группами (секунд)",
  "Telegram cheklovlariga tushmaslik uchun.": "Чтобы не попасть под ограничения Telegram.",
  "Vaqtinchalik xatoda urinishlar soni": "Число попыток при временной ошибке",
  "Kechikkan yuborish chegarasi (daqiqa)": "Порог отложенной отправки (минут)",
  "Server shu vaqtdan ko'proq ishlamay qolsa, o'tib ketgan e'lon yuborilmaydi.":
    "Если сервер простаивает дольше этого времени, пропущенное объявление не отправляется.",
  "Avtomatik javob matni «Avtomatik javoblar» bo'limida tahrirlanadi.":
    "Текст автоматического ответа редактируется в разделе «Автоматические ответы».",
};
