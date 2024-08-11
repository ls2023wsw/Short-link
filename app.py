from flask import Flask, request, redirect, render_template, session, flash
import sqlite3
import random
import string
from datetime import datetime, timedelta
import time
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 数据库初始化
def init_db():
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            short_link TEXT UNIQUE,
            original_url TEXT,
            created_at TEXT,
            expires_at TEXT,
            user_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suffix TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            status TEXT,
            short_link_balance INTEGER DEFAULT 10,
            seven_days_balance INTEGER DEFAULT 999999,
            fourteen_days_balance INTEGER DEFAULT 0,
            thirty_days_balance INTEGER DEFAULT 0,
            three_months_balance INTEGER DEFAULT 0,
            one_year_balance INTEGER DEFAULT 0,
            last_check_in_date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            log_type TEXT,
            description TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 注册用户
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('links.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
        if c.fetchone()[0] > 0:
            flash('用户名已存在')
            return redirect('/register')
        c.execute('INSERT INTO users (username, password, status, short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance, last_check_in_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                  (username, password, 'pending', 10, 999999, 0, 0, 0, 0, None))
        conn.commit()
        conn.close()
        return redirect('/login')
    return render_template('register.html')
@app.route('/<short_link>')
def redirect_to_original(short_link):
    print(f"Received short_link: {short_link}")  # 打印接收到的短链接
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT original_url, expires_at FROM links WHERE short_link = ?', (short_link,))
    result = c.fetchone()
    conn.close()
    
    if result:
        print(f"Found original URL: {result[0]}")  # 打印找到的原链接
        original_url, expires_at = result
        if datetime.strptime(expires_at, "%Y/%m/%d %H:%M:%S") > datetime.now():
            return redirect(original_url)
        else:
            flash('该短链接已过期')
            return redirect('/')
    else:
        print("Short link not found")  # 没有找到对应短链接时输出
        flash('短链接不存在或已过期')
        return redirect('/')
# 用户登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('links.db')
        c = conn.cursor()
        c.execute('SELECT id, status FROM users WHERE username = ? AND password = ?', (username, password))
        user = c.fetchone()
        if user and user[1] == 'approved':
            session['logged_in'] = True
            session['user_id'] = user[0]
            return redirect('/')
        else:
            flash('用户名或密码错误或账户未批准')
            return redirect('/login')
    return render_template('login.html')

# 退出登录
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    return redirect('/login')

# 生成短链接页面
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect('/login')
    user_id = session['user_id']
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance FROM users WHERE id = ?', (user_id,))
    balances = c.fetchone()
    conn.close()
    return render_template('index.html', balances=balances)

# 获取用户的所有短链接
@app.route('/links')
def links():
    if not session.get('logged_in'):
        return redirect('/login')
    user_id = session['user_id']
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT short_link, original_url, created_at, expires_at FROM links WHERE user_id = ?', (user_id,))
    links = c.fetchall()
    conn.close()
    return render_template('links.html', links=links)

# 用户查看自己的日志
@app.route('/user/logs')
def user_logs():
    if not session.get('logged_in'):
        return redirect('/login')
    user_id = session['user_id']
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT log_type, description, created_at FROM logs WHERE user_id = ?', (user_id,))
    logs = c.fetchall()
    conn.close()
    return render_template('user_logs.html', logs=logs)

# 生成短链接逻辑
@app.route('/create', methods=['POST'])
def create_link():
    if not session.get('logged_in'):
        return redirect('/login')
    original_url = request.form['url']
    expiration_days = int(request.form['expiration'])
    user_id = session['user_id']
    # 从数据库获取用户余额
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance FROM users WHERE id = ?', (user_id,))
    user_balances = c.fetchone()
    short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance = user_balances

    # 检查余额是否足够
    if short_link_balance <= 0 or (expiration_days == 7 and seven_days_balance <= 0) or (expiration_days == 14 and fourteen_days_balance <= 0) or (expiration_days == 30 and thirty_days_balance <= 0) or (expiration_days == 90 and three_months_balance <= 0) or (expiration_days == 365 and one_year_balance <= 0):
        log_event(user_id, '生成失败日志', f'因余额不足无法生成 {expiration_days} 天的短链接')
        flash('余额不足，无法生成短链接')
        return redirect('/')

    short_link = generate_unique_short_link()
    created_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    expires_at = (datetime.now() + timedelta(days=expiration_days)).strftime("%Y/%m/%d %H:%M:%S")
    store_link(short_link, original_url, created_at, expires_at, user_id)
    update_user_balance(user_id, expiration_days)

    log_event(user_id, '生成链接日志', f'生成了一个 {expiration_days} 天的短链接: {short_link}')

    return redirect('/links')

# 生成唯一短链接
def generate_unique_short_link():
    suffix_length = 2
    while True:
        short_link = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*()_+=-", k=suffix_length))
        if not is_blacklisted(short_link) and not link_exists(short_link):
            return short_link
        suffix_length += 1

# 检查是否在黑名单中
def is_blacklisted(suffix):
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM blacklist WHERE suffix = ?', (suffix,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# 检查链接是否存在
def link_exists(suffix):
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM links WHERE short_link = ?', (suffix,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# 存储短链接到数据库
def store_link(short_link, original_url, created_at, expires_at, user_id):
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('INSERT INTO links (short_link, original_url, created_at, expires_at, user_id) VALUES (?, ?, ?, ?, ?)',
              (short_link, original_url, created_at, expires_at, user_id))
    conn.commit()
    conn.close()

# 日志记录
def log_event(user_id, log_type, description):
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    created_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    c.execute('INSERT INTO logs (user_id, log_type, description, created_at) VALUES (?, ?, ?, ?)',
              (user_id, log_type, description, created_at))
    conn.commit()
    conn.close()

# 更新用户余额
def update_user_balance(user_id, expiration_days):
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('UPDATE users SET short_link_balance = short_link_balance - 1 WHERE id = ?', (user_id,))
    if expiration_days == 7:
        c.execute('UPDATE users SET seven_days_balance = seven_days_balance - 1 WHERE id = ?', (user_id,))
    elif expiration_days == 14:
        c.execute('UPDATE users SET fourteen_days_balance = fourteen_days_balance - 1 WHERE id = ?', (user_id,))
    elif expiration_days == 30:
        c.execute('UPDATE users SET thirty_days_balance = thirty_days_balance - 1 WHERE id = ?', (user_id,))
    elif expiration_days == 90:
        c.execute('UPDATE users SET three_months_balance = three_months_balance - 1 WHERE id = ?', (user_id,))
    elif expiration_days == 365:
        c.execute('UPDATE users SET one_year_balance = one_year_balance - 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

# 每日签到逻辑
@app.route('/check_in', methods=['POST'])
def check_in():
    if not session.get('logged_in'):
        return redirect('/login')
    
    user_id = session['user_id']
    conn = sqlite3.connect('links.db')
    c = conn.cursor()

    c.execute('SELECT last_check_in_date FROM users WHERE id = ?', (user_id,))
    last_check_in_date = c.fetchone()[0]
    today = datetime.now().strftime("%Y/%m/%d")
    
    if last_check_in_date == today:
        flash('您今天已经签到过了，请明天再来！')
        return redirect('/')

    # 随机增加1到5次短链接次数和一个特定时间类型的短链接次数
    short_link_reward = random.randint(1, 5)
    time_type = random.choice(['seven_days_balance', 'fourteen_days_balance', 'thirty_days_balance', 'three_months_balance', 'one_year_balance'])
    
    c.execute(f'UPDATE users SET short_link_balance = short_link_balance + ?, {time_type} = {time_type} + 1, last_check_in_date = ? WHERE id = ?', 
              (short_link_reward, today, user_id))
    
    conn.commit()
    conn.close()

    flash(f'签到成功，获得了{short_link_reward}次短链接次数和1个特定时间类型的短链接次数奖励！')
    return redirect('/')

# 管理员页面
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'x' and password == 'x':
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        else:
            flash('用户名或密码错误')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    return render_template('admin_dashboard.html')

@app.route('/admin/blacklist', methods=['GET', 'POST'])
def admin_blacklist():
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    if request.method == 'POST':
        suffix = request.form['suffix']
        conn = sqlite3.connect('links.db')
        c = conn.cursor()
        c.execute('INSERT INTO blacklist (suffix) VALUES (?)', (suffix,))
        conn.commit()
        conn.close()
    blacklist = get_blacklist()
    return render_template('admin_blacklist.html', blacklist=blacklist)

@app.route('/admin/delete_blacklist/<suffix>', methods=['POST'])
def delete_blacklist(suffix):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('DELETE FROM blacklist WHERE suffix = ?', (suffix,))
    conn.commit()
    conn.close()
    return redirect('/admin/blacklist')

@app.route('/admin/users')
def admin_users():
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT id, username, status, short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance FROM users')
    users = c.fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/approve_user/<int:user_id>', methods=['POST'])
def approve_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('UPDATE users SET status = "approved" WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/reject_user/<int:user_id>', methods=['POST'])
def reject_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/update_balance/<int:user_id>', methods=['POST'])
def update_balance(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    
    short_link_balance = int(request.form['short_link_balance'])
    seven_days_balance = int(request.form['seven_days_balance'])
    fourteen_days_balance = int(request.form['fourteen_days_balance'])
    thirty_days_balance = int(request.form['thirty_days_balance'])
    three_months_balance = int(request.form['three_months_balance'])
    one_year_balance = int(request.form['one_year_balance'])
    
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('''
        UPDATE users 
        SET short_link_balance = ?, 
            seven_days_balance = ?, 
            fourteen_days_balance = ?, 
            thirty_days_balance = ?, 
            three_months_balance = ?, 
            one_year_balance = ? 
        WHERE id = ?
    ''', (short_link_balance, seven_days_balance, fourteen_days_balance, thirty_days_balance, three_months_balance, one_year_balance, user_id))
    conn.commit()
    conn.close()
    
    return redirect('/admin/users')

@app.route('/admin/logs')
def admin_logs():
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('''
        SELECT users.username, logs.log_type, logs.description, logs.created_at 
        FROM logs 
        JOIN users ON logs.user_id = users.id
    ''')
    logs = c.fetchall()
    conn.close()
    return render_template('admin_logs.html', logs=logs)

def get_blacklist():
    conn = sqlite3.connect('links.db')
    c = conn.cursor()
    c.execute('SELECT suffix FROM blacklist')
    blacklist = [row[0] for row in c.fetchall()]
    conn.close()
    return blacklist

if __name__ == '__main__':
    init_db()
    app.run(port=5222, debug=True)
