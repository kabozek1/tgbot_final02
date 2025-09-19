"""
Клавиатуры для админ панели
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ панели с растянутыми кнопками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Запланировать пост", callback_data="admin:new_post")],
        [InlineKeyboardButton(text="📋 Посты", callback_data="admin:posts")],
        [InlineKeyboardButton(text="🤬 Антимат", callback_data="admin:antimat")],
        [InlineKeyboardButton(text="🔄 Антиспам", callback_data="admin:antispam")],
        [InlineKeyboardButton(text="🛎 Триггеры", callback_data="admin:triggers")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats_detailed")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")]
    ])


def get_stats_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура раздела статистики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Общая статистика", callback_data="admin:stats_overall")],
        [InlineKeyboardButton(text="🔗 Инвайт ссылки", callback_data="admin:stats_invites")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
    ])


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню (с логотипом)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
    ])


def get_post_view_keyboard(post_id: int, status: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра поста с кнопками действий"""
    buttons = []
    
    # Добавляем кнопки только для pending постов
    if status == "pending":
        buttons.append([InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"post_publish:{post_id}")])
        buttons.append([InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"post_edit_time:{post_id}")])
    
    # Кнопка удаления для всех постов
    buttons.append([InlineKeyboardButton(text="🗑️ Удалить пост", callback_data=f"post_delete:{post_id}")])
    
    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin:posts")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_topic_selection_keyboard(topics: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора топика"""
    buttons = []
    processed_chats = set()  # Для отслеживания уже обработанных чатов
    
    for topic in topics:
        topic_id = topic.get('topic_id')
        topic_name = topic.get('topic_name', f'Топик {topic_id}')
        chat_id = topic.get('chat_id')
        
        if topic_id is None:
            # Для основного чата проверяем, не обрабатывали ли мы уже этот чат
            if chat_id not in processed_chats:
                display_name = "Основной чат"
                callback_data = f"post_editor:topic:general:{chat_id}"
                buttons.append([InlineKeyboardButton(text=display_name, callback_data=callback_data)])
                processed_chats.add(chat_id)
        else:
            display_name = f"{topic_name} ({topic_id})"
            callback_data = f"post_editor:topic:{topic_id}:{chat_id}"
            buttons.append([InlineKeyboardButton(text=display_name, callback_data=callback_data)])
    
    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_time_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора времени публикации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сейчас", callback_data="post_editor:time:now")],
        [InlineKeyboardButton(text="Через 5 минут", callback_data="post_editor:time:5min")],
        [InlineKeyboardButton(text="Через 1 час", callback_data="post_editor:time:1hour")],
        [InlineKeyboardButton(text="Через 1 день", callback_data="post_editor:time:1day")],
        [InlineKeyboardButton(text="Ввести вручную", callback_data="post_editor:time:manual")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main_menu")]
    ])


def get_media_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для медиа (можно пропустить)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Добавить медиа", callback_data="post_editor:media:add")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_editor:media:skip")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_editor:back_to_time")]
    ])


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запланировать", callback_data="post_editor:confirm")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_editor:back_to_buttons")]
    ])


def get_buttons_settings_keyboard(buttons_list: list = None, post_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура настроек кнопок поста"""
    if buttons_list is None:
        buttons_list = []
    
    keyboard_buttons = []
    
    # Показываем добавленные кнопки с кнопками удаления
    for button in buttons_list:
        button_text = f"🔘 {button.get('text', 'Кнопка')}"
        button_id = button.get('id', 0)
        keyboard_buttons.append([
            InlineKeyboardButton(text=button_text, callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"post_button:delete:{button_id}")
        ])
    
    # Кнопка добавления новой кнопки
    if post_id:
        # Для существующих постов используем post_buttons:add
        keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="post_buttons:add")])
    else:
        # Для планировщика поста используем post_editor:add_button
        keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="post_editor:add_button")])
    
    # Кнопки навигации
    if post_id:
        # Редактирование существующего поста
        keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к посту", callback_data=f"post_view:{post_id}")])
    else:
        # Создание нового поста
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Продолжить", callback_data="post_editor:confirm")])
        keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="post_editor:back_to_media")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_posts_menu_keyboard() -> InlineKeyboardMarkup:
    """Простое меню выбора типа постов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Запланированные", callback_data="posts_list:pending")],
        [InlineKeyboardButton(text="✅ Отправленные", callback_data="posts_list:published")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
    ])


def get_posts_list_keyboard(posts: list, page: int = 0, per_page: int = 5, post_type: str = "pending") -> InlineKeyboardMarkup:
    """Клавиатура списка постов"""
    buttons = []
    
    # Показываем посты для текущей страницы
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    for post in posts[start_idx:end_idx]:
        post_id = post.get('id')
        publish_time = post.get('publish_time', 'Не указано')
        status = post.get('status', 'pending')
        
        # Форматируем время без микросекунд
        if isinstance(publish_time, str):
            # Если это строка, парсим и форматируем
            from datetime import datetime
            try:
                publish_time_obj = datetime.fromisoformat(publish_time.replace('Z', '+00:00'))
                time_display = publish_time_obj.strftime("%d.%m.%Y %H:%M:%S")
            except:
                time_display = publish_time[:16]  # Fallback - обрезаем до даты и времени
        else:
            # Если это datetime объект
            time_display = publish_time.strftime("%d.%m.%Y %H:%M:%S")
        
        status_emoji = "⏳" if status == "pending" else "✅" if status == "published" else "❌"
        
        button_text = f"{status_emoji} {time_display}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"post_view:{post_id}")])
    
    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"posts_page:{page-1}:{post_type}"))
    
    if end_idx < len(posts):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"posts_page:{page+1}:{post_type}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопка возврата к выбору типа постов
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:posts")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_post_actions_keyboard(post_id: int, status: str = None, has_media: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий с постом"""
    buttons = []
    
    # Кнопка редактирования для всех постов
    buttons.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit:{post_id}")])
    
    # Кнопки для работы с медиа (только для запланированных постов)
    if status == "pending":
        if has_media:
            buttons.append([InlineKeyboardButton(text="🖼️ Заменить медиа", callback_data=f"post_replace_media:{post_id}")])
            buttons.append([InlineKeyboardButton(text="❌ Удалить медиа", callback_data=f"post_remove_media:{post_id}")])
        else:
            buttons.append([InlineKeyboardButton(text="➕ Добавить медиа", callback_data=f"post_add_media:{post_id}")])
    
    # Кнопка изменения времени только для pending постов
    if status == "pending":
        buttons.append([InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"post_edit_time:{post_id}")])
    
    # Кнопка управления кнопками
    buttons.append([InlineKeyboardButton(text="⚙️ Настройки кнопок", callback_data=f"post_buttons:{post_id}")])
    
    # Кнопка "Опубликовать сейчас" только для pending постов
    if status == "pending":
        buttons.append([InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"post_publish:{post_id}")])
    
    # Кнопка удаления
    buttons.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"post_delete:{post_id}")])
    
    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin:posts")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)