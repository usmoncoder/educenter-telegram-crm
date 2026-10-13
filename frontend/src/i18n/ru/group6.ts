// Russian translations — filled by the i18n conversion. Key = Uzbek source string.
export const ru: Record<string, string> = {
  // --- Admins.tsx ---
  "Administratorlar": "Администраторы",
  "Panelga kirish huquqiga ega xodimlar va ularning rollari. Har bir o'zgarish audit jurnaliga yoziladi.":
    "Сотрудники с правом доступа к панели и их роли. Каждое изменение записывается в журнал аудита.",
  "Xodim qo'shish": "Добавить сотрудника",
  "Xodim": "Сотрудник",
  "Holat": "Статус",
  "Oxirgi kirish": "Последний вход",
  " (siz)": " (вы)",
  "Tahrirlash": "Редактировать",
  "{name} yaratildi": "{name} создан",
  "Saqlandi": "Сохранено",
  "Yangi xodim": "Новый сотрудник",
  "Yaratish": "Создать",
  "Login": "Логин",
  "Lotin harflari, raqam, '_', '.', '-'": "Латинские буквы, цифры, '_', '.', '-'",
  "To'liq ism": "Полное имя",
  "Rol": "Роль",
  "Operator": "Оператор",
  "Admin": "Админ",
  "Super Admin": "Супер-админ",
  "Boshlang'ich parol": "Начальный пароль",
  "Tahrirlash: {name}": "Редактирование: {name}",
  "Saqlash": "Сохранить",
  "Akkaunt faol (o'chirilsa, barcha sessiyalari yakunlanadi)":
    "Аккаунт активен (при отключении все его сессии завершаются)",
  "Yangi parol (ixtiyoriy)": "Новый пароль (необязательно)",
  "O'rnatilsa, xodimning barcha sessiyalari yakunlanadi.": "При установке все сессии сотрудника завершаются.",
  "Kamida 12 belgi: kichik va katta harf, raqam, belgilardan kamida uchtasi.":
    "Минимум 12 символов: не менее трёх видов из строчных и прописных букв, цифр и символов.",
  "Barcha sozlamalar, xodimlar, Telegram ulanishi va audit jurnali.":
    "Все настройки, сотрудники, подключение Telegram и журнал аудита.",
  "Kundalik ish: suhbatlar, avtomatik javob, guruhlar, e'lonlar, hisobotlar.":
    "Повседневная работа: диалоги, автоответы, группы, объявления, отчёты.",
  "Faqat o'ziga biriktirilgan (va biriktirilmagan) suhbatlar va javob yozish.":
    "Только назначенные ему (и неназначенные) диалоги и написание ответов.",

  // --- Telegram.tsx ---
  "Telegram ulanishi": "Подключение Telegram",
  "Tizim ulangan Telegram akkaunti va worker holati. Login kodi va 2FA parol veb-panelda hech qachon so'ralmaydi.":
    "Telegram-аккаунт, к которому подключена система, и состояние worker'а. Код входа и пароль 2FA никогда не запрашиваются в веб-панели.",
  "Qayta ulanish": "Переподключить",
  "Bajarilmadi": "Не выполнено",
  "Qayta ulanish boshlandi": "Переподключение начато",
  "Akkaunt": "Аккаунт",
  "Ulangan vaqt": "Время подключения",
  "Worker oxirgi signal": "Последний сигнал worker'а",
  "API kalitlari": "API-ключи",
  "Worker hali xabar bermagan": "Worker ещё не сообщил",
  "Sozlangan": "Настроено",
  "Oxirgi xato": "Последняя ошибка",
  "Ulash yo'riqnomasi": "Инструкция по подключению",
  "sahifasida API_ID va API_HASH oling va serverdagi":
    "— на этой странице получите API_ID и API_HASH и впишите их в файл",
  "fayliga yozing.": "на сервере.",
  "Serverda worker'ni to'xtating:": "Остановите worker на сервере:",
  "Bir martalik kirish ustasini ishga tushiring. Telefon raqam, Telegram yuborgan kod va (agar yoqilgan bo'lsa) 2FA parolni terminalda kiriting:":
    "Запустите мастер одноразового входа. Введите в терминале номер телефона, код от Telegram и (если включён) пароль 2FA:",
  "Worker'ni qayta ishga tushiring — holat bir daqiqa ichida «Telegram ulangan»ga o'zgaradi:":
    "Перезапустите worker — в течение минуты статус изменится на «Telegram подключён»:",
  "Worker to'xtatilgan: xabarlar kuzatilmayapti va hech narsa yuborilmayapti. Serverda ishga tushiring:":
    "Worker остановлен: сообщения не отслеживаются и ничего не отправляется. Запустите на сервере:",
  "Worker {since} dan beri signal bermayapti. Serverda":
    "Worker не подаёт сигнал уже {since}. Проверьте на сервере командами",
  "va": "и",
  "buyruqlari bilan tekshiring.": ".",
  "Ulanish jurnali": "Журнал подключений",
  "Hodisalar yo'q": "Нет событий",
  // Telegram EVENT_LABEL
  "Worker ishga tushdi": "Worker запущен",
  "Telegramga ulandi": "Подключено к Telegram",
  "Aloqa uzildi": "Связь потеряна",
  "Avtorizatsiya talab qilindi": "Требуется авторизация",
  "API kalitlari sozlanmagan": "API-ключи не настроены",
  "Worker to'xtatildi": "Worker остановлен",
  "Qayta ulanish so'raldi": "Запрошено переподключение",

  // --- ConnectionPill.tsx (CONNECTION_LABEL) ---
  "Telegram ulangan": "Telegram подключён",
  "Ishga tushmoqda": "Запускается",
  "Aloqa uzilgan": "Связь потеряна",
  "Kirish talab qilinadi": "Требуется вход",
  "Sozlanmagan": "Не настроено",
  "Kutish rejimi": "Режим ожидания",
  "Ulanish xatosi": "Ошибка подключения",
  "To'xtatilgan": "Остановлено",
  "Worker ishga tushmagan": "Worker не запущен",
  "Worker javob bermayapti": "Worker не отвечает",

  // --- SlaTimer.tsx ---
  "Javob muddati": "Срок ответа",

  // --- MessageEditor.tsx ---
  "Matn kiritilganda shu yerda ko'rinadi": "Здесь появится введённый текст",
  "belgi": "символов",
  "Formatlash": "Форматирование",
  "Havola": "Ссылка",
  "Havola qo'shish": "Добавить ссылку",
  "Telegramda shunday ko'rinadi": "Так будет выглядеть в Telegram",
  "Qo'shish": "Добавить",
  "Manzil": "Адрес",
  "Belgilangan matn havolaga aylanadi.": "Выделенный текст станет ссылкой.",
  "matn": "текст",
  "Qalin": "Жирный",
  "Kursiv": "Курсив",
  "Tagiga chizilgan": "Подчёркнутый",
  "Chizib tashlangan": "Зачёркнутый",
  "Kod": "Код",
  "Iqtibos": "Цитата",

  // --- StatusBadge.tsx (MAP labels) ---
  "Qo'llanmagan": "Не применено",
  "Navbatda": "В очереди",
  "Yuborilmoqda": "Отправляется",
  "Yuborilgan": "Отправлено",
  "Xato": "Ошибка",
  "Eski suhbat": "Старый диалог",
  "Noma'lum": "Неизвестно",
  "Javob berilgan": "Отвечено",
  "Kutmoqda": "Ожидает",
  "Muddati o'tgan": "Просрочено",
  "Ochiq": "Открыто",
  "Yopilgan": "Закрыто",
  "Kerak bo'lmadi": "Не требовалось",
  "Yuborildi": "Отправлено",
  "Qoralama": "Черновик",
  "Faol": "Активно",
  "Yakunlangan": "Завершено",
  "Bekor qilingan": "Отменено",
  "Kutilmoqda": "Ожидание",
  "Bajarilmoqda": "Выполняется",
  "Bajarildi": "Выполнено",
  "Qisman": "Частично",
  "O'tkazib yuborildi": "Пропущено",
  "O'tkazildi": "Пропущено",
  "Sinov": "Тест",

  // --- ui/Layout.tsx ---
  "Yuklanmoqda…": "Загрузка…",
  "Ma'lumotni yuklab bo'lmadi": "Не удалось загрузить данные",
  "Qayta urinish": "Повторить",
  "Sahifalar": "Страницы",
  "Oldingi sahifa": "Предыдущая страница",
  "Keyingi sahifa": "Следующая страница",

  // --- ui/Modal.tsx ---
  "Yopish": "Закрыть",

  // --- shared across files ---
  "Bekor qilish": "Отмена",
};
