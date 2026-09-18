from flask import Flask, render_template
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask import Flask, render_template, request
import time # 用於產生唯一 ID
import google.generativeai as genai
import json
import os
import random # 蘋果產生位置

genai.configure(api_key="AIzaSyCVjDyN6Sd3qYC057ZDnowWuGAVj2pqqT4")
model = genai.GenerativeModel('gemini-2.5-flash') # 使用最新的輕量模型




app = Flask(__name__)
app.config['SECRET_KEY'] = 'discord_clone_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")
DATA_FILE = 'discord_data.json'



# 用來儲存每個房間的對話歷史
CHANNEL_HISTORY = {}
CONNECTED_USERS = {}
GAMES_STATE = {} # 紀錄聊天室蛇的座標方向

# 讀取資料：伺服器啟動時呼叫
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    # 如果檔案不存在 回傳預設的資料結構
    return {
        "servers": {
            "server_default": {"name": "中山猴管系", "channels": ["綜合討論"]}
        },
        "history": {}
    }

# 儲存資料：每次有新訊息、新 Server 時呼叫
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 伺服器啟動時，把資料載入到全域變數 ---
global_data = load_data()
SERVERS_DATA = global_data["servers"]
CHANNEL_HISTORY = global_data["history"]





@app.route('/')
def index():
    # 將整個多群組資料傳給前端
    return render_template('index.html', servers=SERVERS_DATA)

@socketio.on('join_channel')
def handle_join(data):
    username = data.get('username', '匿名者')
    server = data.get('server')
    channel = data.get('channel')
    old_room = data.get('old_room') # 格式會是 "server_id:channel_name"

    # 新房間的唯一識別碼
    new_room = f"{server}:{channel}"

    if old_room and old_room != new_room:
        leave_room(old_room)
        emit('system_message', {'msg': f'{username} 離開了頻道。'}, room=old_room)

    join_room(new_room)
#  將使用者的 Socket ID 與他的暱稱、所在房間綁定起來記錄
    CONNECTED_USERS[request.sid] = {
        "username": username,
        "room": new_room
    }


    emit('system_message', {'msg': f'{username} 已加入頻道！'}, room=new_room)
    update_room_users(new_room)  # 加入新房間時，通知all更新名單



@socketio.on('send_chat')
def handle_chat(data):
    username = data.get('username', '匿名者')
    message = data.get('message')
    server = data.get('server')
    channel = data.get('channel')
    
    #抓取前端傳來的遊戲模式標籤（如果沒傳，預設為 False）
    is_game_command = data.get('is_game_command', False)

    # 組合出唯一的房間 ID
    room_id = f"{server}:{channel}"
    
# 貪食蛇指令攔截網  
    msg_lower = message.lower()
    # 定義有效指令與對應方向
    valid_commands = {
        'w': 'up', 's': 'down', 'a': 'left', 'd': 'right',
        '上': 'up', '下': 'down', '左': 'left', '右': 'right',
        'start_game': 'start'
    }
    
    if is_game_command and msg_lower in valid_commands:
        new_direction = valid_commands[msg_lower]
        

        # 若房間還沒有遊戲，初始化一隻蛇
        if room_id not in GAMES_STATE:
            GAMES_STATE[room_id] = {
                'snake': [[10, 5], [9, 5], [8, 5]], # 初始座標 (X, Y)
                'direction': 'right',
                'apple': [random.randint(0, 29), random.randint(0, 14)] # 畫面網格設為 30x10
            }
        
        if new_direction == 'start':
            return # 如果只是打開遊戲，初始化完就直接結束，不廣播訊息！

        # 避免蛇直接「180度回頭」咬死自己
        current_dir = GAMES_STATE[room_id]['direction']
        opposite_dirs = {'up': 'down', 'down': 'up', 'left': 'right', 'right': 'left'}
        
        if opposite_dirs.get(current_dir) != new_direction:
            GAMES_STATE[room_id]['direction'] = new_direction
            
        # 廣播系統訊息誰在輸入指令
        emit('system_message', {'msg': f'🕹️ {username} 按下了 {msg_lower.upper()}'}, room=room_id)
        return # 攔截成功直接退出 不作一般聊天訊息




    # 確保該房間有對話陣列可以存
    if room_id not in CHANNEL_HISTORY:
        CHANNEL_HISTORY[room_id] = []
        
    # 把對話記錄塞進去(限制最多存50筆)
    history = CHANNEL_HISTORY[room_id]
    history.append(f"{username}: {message}")
    if len(history) > 50:
        history.pop(0)
    
    emit('new_chat', {
        'username': username,
        'message': message
    }, room=room_id)
    

@socketio.on('create_server')
def handle_create_server(data):
    server_name = data.get('name')
    if not server_name: return
    
    # 產生唯一的 Server ID (使用時間戳記)
    server_id = f"server_{int(time.time())}"
    
    # 更新後端全域字典
    SERVERS_DATA[server_id] = {
        "name": server_name,
        "channels": ["討論", "猴猴專區"] # 預設頻道
    }
    
    # 廣播給有新Server
    emit('new_server_created', {
        "server_id": server_id,
        "server_info": SERVERS_DATA[server_id]
    }, broadcast=True) 
    save_data({"servers": SERVERS_DATA, "history": CHANNEL_HISTORY})

# 當有人直接關閉網頁 網路斷線時自動觸發
@socketio.on('disconnect')
def handle_disconnect():
    user_info = CONNECTED_USERS.get(request.sid)
    if user_info:
        room = user_info['room']
        username = user_info['username']
        # 從在線名單中移除
        del CONNECTED_USERS[request.sid]
        
        # 廣播給該房間的其他人
        emit('system_message', {'msg': f'{username} 斷線離開了。'}, room=room)
        update_room_users(room) # ▼ 更新房間名單

# 收集特定房間內的所有人，並廣播更新指令
def update_room_users(room):
    # 利用 List Comprehension 找出所有在該 room 的 username
    users_in_room = [info['username'] for sid, info in CONNECTED_USERS.items() if info['room'] == room]
    
    # 利用set()去除重複的名字，然後廣播給該房間
    socketio.emit('online_users', {'users': list(set(users_in_room))}, room=room)



@socketio.on('request_summary')
def handle_summary(data):
    server = data.get('server')
    channel = data.get('channel')
    room_id = f"{server}:{channel}"
    
    # 1. 從剛剛建立的字典中拿出歷史紀錄
    history = CHANNEL_HISTORY.get(room_id, [])
    
    filtered_history = [line for line in history if "data:image/" not in line]

    # 防呆機制：訊息太少不浪費 API 額度了
    if len(history) < 3:
        emit('system_message', {'msg': '對話太少啦，AI 覺得沒什麼好總結的 😴'}, room=room_id)
        return

    # 2. 將陣列組合成字串
    chat_log = "\n".join(filtered_history)
    
    # 3. 設計嚴格的 System Prompt 降低幻覺發生率
    prompt = f"""
    你是一個客觀的群組聊天室 AI 助理。請根據以下對話紀錄，用繁體中文寫出1~3點的簡短總結。
    
    【嚴格限制】：
    1. 只能基於提供的紀錄進行摘要，絕對不可捏造或推論未提及的資訊。
    2. 如果對話毫無意義（例如只是互相打招呼），請直接回覆「目前尚無具體討論內容」。
    3. 語氣請保持精簡、友善。
    
    對話紀錄：
    {chat_log}
    """
    
    try:
        # 先廣播告訴大家 AI 正在看訊息
        emit('system_message', {'msg': '✨ AI 小幫手正在生成摘要，請稍候...'}, room=room_id)
        
        # 呼叫 Gemini API
        response = model.generate_content(prompt)
        
        # 將結果化身為機器人發送回頻道
        emit('new_chat', {
            'username': '🤖 [AI 小幫手]',
            'message': response.text
        }, room=room_id)
        
    except Exception as e:
        # API 發生錯誤（例如網路斷線或額度用盡）的例外處理
        print(f"Gemini API 錯誤: {e}")
        emit('system_message', {'msg': 'AI 似乎出錯了，請稍後再試。'}, room=room_id)



### 5.25 增加重新命名

@socketio.on('rename_server')
def handle_rename_server(data):
    server_id = data.get('server_id')
    new_name = data.get('new_name', '').strip()
    
    if server_id in SERVERS_DATA and new_name:
        SERVERS_DATA[server_id]['name'] = new_name
        # 存入 JSON
        save_data({"servers": SERVERS_DATA, "history": CHANNEL_HISTORY})
        # 廣播給所有人
        emit('server_renamed', {'server_id': server_id, 'new_name': new_name}, broadcast=True)

@socketio.on('rename_channel')
def handle_rename_channel(data):
    server_id = data.get('server_id')
    old_channel = data.get('old_channel')
    new_channel = data.get('new_channel', '').strip()
    
    if server_id in SERVERS_DATA and old_channel in SERVERS_DATA[server_id]['channels'] and new_channel:
        # 1. 修改頻道陣列裡的名字
        channels = SERVERS_DATA[server_id]['channels']
        idx = channels.index(old_channel)
        channels[idx] = new_channel
        
        # 2. 同步變更對話歷史紀錄的 Room ID Key (格式為 server_id:channel_name)
        old_room = f"{server_id}:{old_channel}"
        new_room = f"{server_id}:{new_channel}"
        if old_room in CHANNEL_HISTORY:
            CHANNEL_HISTORY[new_room] = CHANNEL_HISTORY.pop(old_room)
            
        save_data({"servers": SERVERS_DATA, "history": CHANNEL_HISTORY})
        emit('channel_renamed', {'server_id': server_id, 'old_channel': old_channel, 'new_channel': new_channel}, broadcast=True)

@socketio.on('delete_channel')
def handle_delete_channel(data):
    server_id = data.get('server_id')
    channel_name = data.get('channel')
    
    if server_id in SERVERS_DATA and channel_name in SERVERS_DATA[server_id]['channels']:
        # 1. 從陣列刪除
        SERVERS_DATA[server_id]['channels'].remove(channel_name)
        
        # 2. 刪除對應的對話歷史
        room_id = f"{server_id}:{channel_name}"
        if room_id in CHANNEL_HISTORY:
            del CHANNEL_HISTORY[room_id]
            
        save_data({"servers": SERVERS_DATA, "history": CHANNEL_HISTORY})
        emit('channel_deleted', {'server_id': server_id, 'channel': channel_name}, broadcast=True)

# 增加頻道
@socketio.on('create_channel')
def handle_create_channel(data):
    server_id = data.get('server_id')
    channel_name = data.get('channel_name', '').strip()
    
    # 確保伺服器存在，且頻道名稱不為空
    if server_id in SERVERS_DATA and channel_name:
        # 防呆：檢查頻道名稱是不是已經存在了
        if channel_name not in SERVERS_DATA[server_id]['channels']:
            SERVERS_DATA[server_id]['channels'].append(channel_name)
            
            # 存入 JSON 資料庫
            save_data({"servers": SERVERS_DATA, "history": CHANNEL_HISTORY})
            
            # 廣播給所有連線中的使用者，告訴他們有新頻道誕生了
            emit('channel_created', {
                'server_id': server_id,
                'channel_name': channel_name
            }, broadcast=True)




#  貪食蛇背景遊戲引擎 
def game_loop():
    while True:
        socketio.sleep(0.5)  # 遊戲速度：每 0.5 秒前進一格
        
        for room_id, game in list(GAMES_STATE.items()):
            head_x, head_y = game['snake'][0]
            direction = game['direction']
            
            # 根據方向計算下一個座標
            if direction == 'up': head_y -= 1
            elif direction == 'down': head_y += 1
            elif direction == 'left': head_x -= 1
            elif direction == 'right': head_x += 1
            
            # 穿牆機制：超出邊界就從另一邊出來 (網格設為寬30, 高10)
            head_x %= 30
            head_y %= 15
            
            new_head = [head_x, head_y]
            
            # 更新蛇的身體
            game['snake'].insert(0, new_head)
            
            # 檢查有沒有吃到蘋果
            if new_head == game['apple']:
                # 吃到蘋果：身體不縮短，產生新蘋果
                game['apple'] = [random.randint(0, 29), random.randint(0, 9)]
            else:
                # 沒吃到蘋果：尾巴縮短一格，保持長度
                game['snake'].pop()
                
            # 將最新座標廣播給該房間的所有人！
            socketio.emit('game_update', {
                'snake': game['snake'], 
                'apple': game['apple']
            }, room=room_id)

# 讓 SocketIO 在背景啟動這個引擎
socketio.start_background_task(game_loop)
#  引擎設定結束 

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)