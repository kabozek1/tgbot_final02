import os
import importlib
from aiogram import Dispatcher, Bot
from sqlalchemy.ext.asyncio import async_sessionmaker # Import async_sessionmaker


def register_plugins(dp: Dispatcher, bot: Bot, async_session_local: async_sessionmaker):
    """
    Register all plugins from src/plugins directory.
    
    Args:
        dp: Dispatcher instance
        bot: Bot instance
        async_session_local: The AsyncSessionLocal factory for database access
    """
    print(f"🔍 DEBUG: register_plugins called with async_session_local type={type(async_session_local)}")
    print(f"🔍 DEBUG: bot type={type(bot)}")
    print(f"🔍 DEBUG: async_session_local repr: {repr(async_session_local)}")
    plugins_dir = os.path.dirname(__file__)
    plugins_path = os.path.join(plugins_dir, 'plugins')
    
    # List of plugins to register in specific order
    plugin_order = [
        'admin_panel',  # Новая упрощенная админ панель
        'scheduler_plugin',
        'post_manager_plugin',
        
        # Specific commands and text triggers should be registered BEFORE filters
        'hello_plugin',
        'triggers_plugin',  # Moved before blacklist_plugin to ensure triggers work
        'warn_plugin',
        'mute_plugin',
        'ban_plugin',
        'poll_plugin',
        'reputation_plugin',
        
        # Filters should be registered AFTER specific handlers but BEFORE stats
        'blacklist_plugin',  # Moved after triggers_plugin
        'antiflood_plugin',  # Moved before stats_plugin
        
        'invite_stats',  # Плагин статистики инвайт-ссылок (должен быть перед stats_plugin)
        'stats_plugin',
        
        'captcha_plugin',
        'delete_plugin'
    ]
    
    # Register plugins in order
    for plugin_name in plugin_order:
        try:
            # Import plugin module
            module = importlib.import_module(f'plugins.{plugin_name}')
            
            # Call register function if it exists
            if hasattr(module, 'register'):
                print(f"🔍 DEBUG: About to register plugin '{plugin_name}' with async_session_local type={type(async_session_local)}")
                # Pass bot and async_session_local to the register function
                try:
                    module.register(dp, bot, async_session_local)
                    print(f"✅ Registered plugin: {plugin_name}")
                    # Debug: show registered handlers count
                    handlers_count = len(dp.message.handlers)
                    print(f"🔍 DEBUG: Total message handlers after {plugin_name}: {handlers_count}")
                except Exception as reg_error:
                    print(f"❌ Error in register function for {plugin_name}: {reg_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"❌ Plugin {plugin_name} has no register function")
                
        except ImportError as e:
            print(f"❌ Failed to import plugin {plugin_name}: {e}")
        except Exception as e:
            print(f"❌ Error registering plugin {plugin_name}: {e}")
    
    # Also register any other plugins not in the list
    for filename in os.listdir(plugins_path):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]  # Remove .py extension
            
            # Skip if already registered
            if module_name in plugin_order:
                continue
                
            try:
                # Import plugin module
                module = importlib.import_module(f'plugins.{module_name}')
                
                # Call register function if it exists
                if hasattr(module, 'register'):
                    # Pass bot and async_session_local to the register function
                    module.register(dp, bot, async_session_local)
                    print(f"✅ Registered additional plugin: {module_name}")
                    
            except ImportError as e:
                print(f"❌ Failed to import additional plugin {module_name}: {e}")
            except Exception as e:
                print(f"❌ Error registering additional plugin {module_name}: {e}")