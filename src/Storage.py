# storage.py
# 全局用户存储
user_storage = {}

# 当前处理的用户ID（简单全局状态）
current_processing_user = None

# 可以添加一些辅助函数
def add_user(user_id, user_data):
    """添加或更新用户信息"""
    user_storage[user_id] = user_data

def get_user(user_id):
    """获取特定用户信息"""
    return user_storage.get(user_id)

def set_processing_user(user_id):
    """设置当前正在处理的用户ID"""
    global current_processing_user
    current_processing_user = user_id

def get_processing_user():
    """获取当前正在处理的用户ID"""
    return current_processing_user

def get_all_users():
    return user_storage

def delete_user(user_id):
    if user_id in user_storage:
        del user_storage[user_id]
        return True
    return False
