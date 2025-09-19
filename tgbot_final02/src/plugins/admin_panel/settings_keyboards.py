"""
Клавиатуры для настроек админ панели
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_settings_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление администраторами", callback_data="settings:admins")],
        [InlineKeyboardButton(text="📈 Статус системы", callback_data="admin:status")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
    ])


def get_admin_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления администраторами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="admin_management:add")],
        [InlineKeyboardButton(text="👥 Список администраторов", callback_data="admin_management:list")],
        [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="admin:settings")]
    ])


def get_admin_list_keyboard(admins: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура списка администраторов"""
    buttons = []
    
    # Показываем администраторов для текущей страницы
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    for admin in admins[start_idx:end_idx]:
        admin_id = admin.get('telegram_id')
        role = admin.get('role', 'admin')
        username = admin.get('username', 'Неизвестно')
        source = admin.get('source', 'db')
        
        # Формируем текст кнопки
        # Админы из конфига отображаются как суперадмины, из БД - как админы
        if source == 'config':
            emoji = '👑'
            role_display = 'Супер-админ'
        else:
            emoji = '👤'
            role_display = 'Администратор'
        
        button_text = f"{emoji} {username} ({role_display})"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"admin_view:{admin_id}")])
    
    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_list_page:{page-1}"))
    
    if end_idx < len(admins):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_list_page:{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:admins")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_actions_keyboard(admin_id: int, current_user_id: int, can_delete: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура действий с администратором"""
    buttons = []
    
    # Кнопка удаления (только если это не текущий пользователь и можно удалять)
    if admin_id != current_user_id and can_delete:
        buttons.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin_delete:{admin_id}")])
    
    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_management:list")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_add_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для добавления администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:admins")]
    ])


def get_role_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора роли администратора (не используется - роль назначается автоматически)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_management:add")]
    ])
