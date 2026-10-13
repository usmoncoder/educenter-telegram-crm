// Russian translations — filled by the i18n conversion. Key = Uzbek source string.
export const ru: Record<string, string> = {
  // Campaigns.tsx — scheduleText
  "Bir marta, {time}": "Однократно, {time}",
  "Bir marta, faollashtirilganda": "Однократно, при активации",
  "{date} dan": "с {date}",
  "{date} gacha": "до {date}",
  "Har kuni {time}": "Ежедневно в {time}",
  "Har hafta: {days}, {time}": "Еженедельно: {days}, {time}",

  // Campaigns.tsx — list page
  "Rejalashtirilgan xabarlar": "Запланированные сообщения",
  "Tanlangan Telegram guruhlariga darhol, belgilangan vaqtda yoki takroriy yuboriladigan e'lonlar.":
    "Объявления, отправляемые в выбранные Telegram-группы сразу, в заданное время или повторно.",
  "Yangi e'lon": "Новое объявление",
  "Hali e'lonlar yo'q": "Пока нет объявлений",
  "Avval «Telegram guruhlari» bo'limida kerakli guruhlarni yoqing, so'ng e'lon yarating.":
    "Сначала включите нужные группы в разделе «Telegram-группы», затем создайте объявление.",
  "Birinchi e'lonni yaratish": "Создать первое объявление",
  "E'lon": "Объявление",
  "Jadval": "Расписание",
  "Guruhlar": "Группы",
  "Keyingi yuborish": "Следующая отправка",
  "Oxirgi natija": "Последний результат",
  "Holat": "Статус",
  "Sinov rejimi": "Тестовый режим",

  // CampaignEditor.tsx — toasts
  "E'lon qoralama sifatida saqlandi": "Объявление сохранено как черновик",
  "O'zgarishlar saqlandi": "Изменения сохранены",
  "E'lon faollashtirildi": "Объявление активировано",
  "Yuborish navbatga qo'yildi": "Отправка поставлена в очередь",
  "E'lon to'xtatildi": "Объявление остановлено",
  "E'lon davom ettirildi": "Объявление возобновлено",
  "E'lon bekor qilindi": "Объявление отменено",

  // CampaignEditor.tsx — validation
  "Sarlavha kiriting": "Введите заголовок",
  "Kamida bitta guruh tanlang": "Выберите хотя бы одну группу",
  "Asosiy matnni yozing": "Введите основной текст",
  "Hafta kunlarini tanlang": "Выберите дни недели",
  "Yuborish vaqtini kiriting": "Укажите время отправки",

  // CampaignEditor.tsx — header & actions
  "Avval qoralama sifatida saqlanadi. Yuborish faqat siz faollashtirgandan keyin boshlanadi.":
    "Сначала сохраняется как черновик. Отправка начнётся только после активации.",
  "Faollashtirish": "Активировать",
  "Jadvalni yoqish": "Включить расписание",
  "To'xtatish": "Остановить",
  "Davom ettirish": "Продолжить",
  "Hozir yuborish": "Отправить сейчас",
  "Bekor qilish": "Отмена",
  "Saqlanmagan o'zgarishlar bor. Yuborishdan oldin saqlang.":
    "Есть несохранённые изменения. Сохраните перед отправкой.",
  "Sinov rejimi yoqilgan: jadval ishlaydi va natija tarixda ko'rinadi, lekin guruhlarga hech narsa yuborilmaydi.":
    "Тестовый режим включён: расписание работает и результат отображается в истории, но в группы ничего не отправляется.",

  // CampaignEditor.tsx — message panel
  "Xabar": "Сообщение",
  "Sarlavha": "Заголовок",
  "Faqat panelda ko'rinadi, guruhga yuborilmaydi.": "Виден только в панели, в группу не отправляется.",
  "Masalan: Kuzgi qabul": "Например: Осенний набор",
  "Asosiy matn (barcha guruhlar uchun)": "Основной текст (для всех групп)",

  // CampaignEditor.tsx — groups panel
  "{count} ta tanlangan": "Выбрано: {count}",
  "E'lonlar uchun yoqilgan guruh yo'q": "Нет групп, включённых для объявлений",
  "«Telegram guruhlari» bo'limida guruhlarni yangilang va kerakli guruhlarni yoqing.":
    "Обновите группы в разделе «Telegram-группы» и включите нужные.",
  "Guruhlarga o'tish": "Перейти к группам",
  "Guruh #{id}": "Группа №{id}",
  "Yozish huquqi yo'q": "Нет прав на отправку",
  "Guruh e'lonlar uchun o'chirilgan": "Группа отключена для объявлений",
  "Bu guruh uchun alohida matn": "Отдельный текст для этой группы",
  "Asosiy matnni ishlatish": "Использовать основной текст",

  // CampaignEditor.tsx — schedule panel
  "Jadval turi": "Тип расписания",
  "Bir marta": "Однократно",
  "Har kuni": "Ежедневно",
  "Hafta kunlari bo'yicha": "По дням недели",
  "Yuborish vaqti (Toshkent)": "Время отправки (Ташкент)",
  "Bo'sh qoldirsangiz, faollashtirilganda darhol yuboriladi.":
    "Если оставить пустым, отправка начнётся сразу после активации.",
  "Vaqt (Toshkent)": "Время (Ташкент)",
  "Hafta kunlari": "Дни недели",
  "Boshlanish": "Начало",
  "Tugash": "Окончание",
  "Hamma narsa tekshiriladi va tarixga yoziladi, lekin xabar yuborilmaydi.":
    "Всё проверяется и записывается в историю, но сообщение не отправляется.",
  "Qoralamani saqlash": "Сохранить черновик",
  "O'zgarishlarni saqlash": "Сохранить изменения",

  // CampaignEditor.tsx — status panel
  "Oxirgi ishga tushish": "Последний запуск",
  "Yaratilgan": "Создано",

  // CampaignEditor.tsx — runs history
  "Yuborishlar tarixi": "История отправок",
  "Hali yuborilmagan": "Ещё не отправлялось",
  "Rejalashtirilgan vaqt": "Запланированное время",
  "Natija": "Результат",
  "Yuborildi": "Отправлено",
  "Xato": "Ошибки",
  "O'tkazildi": "Пропущено",
  "Tugadi": "Завершено",
  "qo'lda": "вручную",
  "Har bir guruh bo'yicha batafsil natija va xato sabablari":
    "Подробный результат по каждой группе и причины ошибок",
  "Xabarlar tarixi": "История сообщений",
  "bo'limida.": "в разделе.",

  // CampaignEditor.tsx — confirm dialogs
  "Sinov rejimi: xabar guruhlarga yuborilmaydi, faqat tekshiriladi.":
    "Тестовый режим: сообщение не отправляется в группы, только проверяется.",
  "{count} ta guruhga": "{count} группам",
  "darhol": "немедленно",
  "jadval bo'yicha": "по расписанию",
  "yuboriladi:": "будет отправлено:",
  "va yana {count} ta": "и ещё {count}",
  "Ha, yuborish": "Да, отправить",
  "Ha, yoqish": "Да, включить",
  "E'lonni bekor qilish": "Отменить объявление",
  "Navbatdagi barcha yuborishlar bekor qilinadi. Bekor qilingan e'lonni qayta tiklab bo'lmaydi — kerak bo'lsa yangisini yarating.":
    "Все отправки в очереди будут отменены. Отменённое объявление нельзя восстановить — при необходимости создайте новое.",

  // Groups.tsx — toasts & command results
  "Buyruq bajarilmadi": "Команда не выполнена",
  "Guruhlar yangilandi: {count} ta topildi": "Группы обновлены: найдено {count}",
  "Guruh qo'shildi: {title}": "Группа добавлена: {title}",
  "«{title}» e'lonlar uchun yoqildi": "«{title}» включена для объявлений",
  "«{title}» e'lonlar uchun o'chirildi": "«{title}» отключена для объявлений",
  "Guruh ro'yxatdan o'chirildi": "Группа удалена из списка",

  // Groups.tsx — header & actions
  "Telegram guruhlari": "Telegram-группы",
  "Akkaunt a'zo bo'lgan guruhlar. E'lon yuborish uchun guruhni alohida yoqish kerak — tizim hech qachon tanlanmagan guruhga yozmaydi.":
    "Группы, в которых состоит аккаунт. Чтобы отправлять объявления, группу нужно включить отдельно — система никогда не пишет в невыбранную группу.",
  "Qo'lda qo'shish": "Добавить вручную",
  "Guruhlarni yangilash": "Обновить группы",

  // Groups.tsx — status notice & empty state
  "Buyruq worker'ga yuborildi. Telegram ulangan bo'lsa, bir necha soniyada bajariladi…":
    "Команда отправлена воркеру. Если Telegram подключён, выполнится через несколько секунд…",
  "Telegram'dan ma'lumot olinmoqda…": "Получение данных из Telegram…",
  "Guruhlar hali yuklanmagan": "Группы ещё не загружены",
  "«Guruhlarni yangilash» tugmasi akkaunt a'zo bo'lgan guruhlarni Telegram'dan oladi.":
    "Кнопка «Обновить группы» загружает из Telegram группы, в которых состоит аккаунт.",

  // Groups.tsx — table
  "Guruh": "Группа",
  "Turi": "Тип",
  "A'zolar": "Участники",
  "Yozish huquqi": "Право на отправку",
  "Yangilangan": "Обновлено",
  "E'lonlar uchun": "Для объявлений",
  ", qo'lda qo'shilgan": ", добавлено вручную",
  "Bor": "Есть",
  "Yo'q": "Нет",
  "«{title}» e'lonlar uchun": "«{title}» для объявлений",
  "{title} ni o'chirish": "Удалить {title}",

  // Groups.tsx — KIND values
  "Superguruh": "Супергруппа",
  "Kanal": "Канал",

  // Groups.tsx — manual add modal & delete dialog
  "Guruhni qo'lda qo'shish": "Добавить группу вручную",
  "Tekshirish va qo'shish": "Проверить и добавить",
  "Guruh username, havola yoki ID": "Username, ссылка или ID группы",
  "Masalan: @ielts_guruh, https://t.me/ielts_guruh yoki -1001234567890. Akkaunt avval guruhga a'zo bo'lishi kerak; tizim guruhga qo'shilmaydi.":
    "Например: @ielts_guruh, https://t.me/ielts_guruh или -1001234567890. Аккаунт сначала должен состоять в группе; система не вступает в группу.",
  "Guruhni ro'yxatdan o'chirish": "Удалить группу из списка",
  "«{title}» CRM ro'yxatidan o'chiriladi. Telegramdagi guruhga ta'sir qilmaydi. E'lonlarda ishlatilgan guruhni o'chirib bo'lmaydi.":
    "«{title}» будет удалена из списка CRM. На группу в Telegram это не влияет. Группу, использованную в объявлениях, удалить нельзя.",
  "O'chirish": "Удалить",
};
