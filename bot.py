import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, SlashOption
import os
import json
import asyncio
from gtts import gTTS
from pydub import AudioSegment
from pydub.utils import which
import re

intents = nextcord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='/', intents=intents)

SETTINGS_FILE = 'tts_settings.json'

##############################################
# 서버별 설정 로드/저장 함수들
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

def get_server_settings(guild_id):
    settings = load_settings()
    if str(guild_id) not in settings:
        settings[str(guild_id)] = {"auto_tts": True, "chat_tts": True, "dm_tts": True}
        save_settings(settings)
    return settings[str(guild_id)]

def update_server_settings(guild_id, key, value):
    settings = load_settings()
    if str(guild_id) not in settings:
        settings[str(guild_id)] = {"auto_tts": True, "chat_tts": True, "dm_tts": True}
    settings[str(guild_id)][key] = value
    save_settings(settings)

# on_ready 이벤트
@bot.event
async def on_ready():
    print(f"봇이 {len(bot.guilds)}개의 서버에 접속되었습니다:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id})")
    if not check_voice_channels.is_running():
        check_voice_channels.start()

##############################################
# 슬래시 명령어 (설정 관련)

@bot.slash_command(name='tts자동참가', description='TTS 자동 참가 기능을 ON/OFF 합니다.')
async def toggle_auto_tts(interaction: Interaction, 상태: str = SlashOption(choices=["ON", "OFF"])):
    guild_id = interaction.guild.id
    state = (상태 == "ON")
    update_server_settings(guild_id, "auto_tts", state)
    embed = nextcord.Embed(
        title="🔊 TTS 자동 참가 설정 변경",
        description=f"현재 상태: **{상태}**",
        color=0x00ff00 if state else 0xff0000
    )
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name='tts채팅반응', description='TTS가 음성 채널 내 채팅에 반응할지 설정합니다.')
async def toggle_chat_tts(interaction: Interaction, 상태: str = SlashOption(choices=["ON", "OFF"])):
    guild_id = interaction.guild.id
    state = (상태 == "ON")
    update_server_settings(guild_id, "chat_tts", state)
    embed = nextcord.Embed(
        title="💬 TTS 채팅 반응 설정 변경",
        description=f"현재 상태: **{상태}**",
        color=0x00ff00 if state else 0xff0000
    )
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name='ttsdm반응', description='TTS가 DM 메시지에 반응할지 설정합니다.')
async def toggle_dm_tts(interaction: Interaction, 상태: str = SlashOption(choices=["ON", "OFF"])):
    guild_id = interaction.guild.id
    state = (상태 == "ON")
    update_server_settings(guild_id, "dm_tts", state)
    embed = nextcord.Embed(
        title="📩 TTS DM 반응 설정 변경",
        description=f"현재 상태: **{상태}**",
        color=0x00ff00 if state else 0xff0000
    )
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name='tts설정확인', description='현재 서버의 TTS 설정을 확인합니다.')
async def check_tts_settings(interaction: Interaction):
    guild_id = interaction.guild.id
    settings = get_server_settings(guild_id)
    embed = nextcord.Embed(title="🔧 현재 TTS 설정", color=0x00ff00)
    embed.add_field(name="자동 참가", value="✅ ON" if settings["auto_tts"] else "❌ OFF", inline=False)
    embed.add_field(name="채팅 반응", value="✅ ON" if settings["chat_tts"] else "❌ OFF", inline=False)
    embed.add_field(name="DM 반응", value="✅ ON" if settings["dm_tts"] else "❌ OFF", inline=False)
    await interaction.response.send_message(embed=embed)


# 특수문자 처리 함수
def process_special_text(text):
    mapping = {
        '?': '물음표',
        '!': '느낌표',
        '@': '골뱅이',
        '#': '샵',
        '$': '달러',
        '%': '퍼센트',
        '^': '캐럿',
        '&': '앤드',
        '*': '별표',
        '(': '왼쪽괄호',
        ')': '오른쪽괄호',
        '-': '대시',
        '+': '더하기',
        '=': '같음',
        '/': '슬래시',
        '\\': '역슬래시',
        ':': '콜론',
        ';': '세미콜론',
        ',': '쉼표',
        '.': '마침표',
        '<': '작다',
        '>': '크다',
        '~': '틸드',
        'ㅇㅎ': '아하',
        'ㅗ': '엿',
        'ㄹㅈㄷ': '래전드',
        'ㅅ': 'ㅅㅂ',
        'ㄹㅇ': '리얼',
        'ㅇㅈ': '인정',
        'ㅈㄹ': 'ㅈㄹ'
    }
    result = ""
    for char in text:
        if char in mapping:
            result += mapping[char] + " "
        else:
            result += char
    return result.strip()

def prepare_text(text):
    # 만약 텍스트에 하나 이상의 영문, 숫자, 한글 등이 있다면 그대로 사용
    if re.search(r'[\w가-힣]', text):
        return text
    # 그렇지 않다면 특수문자만 있으므로 변환
    return process_special_text(text)

##############################################
# TTSPlayer 클래스 / 대기열
class TTSPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}      # {channel_id: VoiceClient}
        self.queues = {}             # {channel_id: asyncio.Queue}, 각 항목은 (job_type, text)
        self.queue_tasks = {}        # {channel_id: asyncio.Task}

    async def join_and_queue(self, text, voice_channel, job_type="normal"):
        if voice_channel.id not in self.voice_clients:
            vc = await voice_channel.connect()
            self.voice_clients[voice_channel.id] = vc
        else:
            vc = self.voice_clients[voice_channel.id]

        if voice_channel.id not in self.queues:
            self.queues[voice_channel.id] = asyncio.Queue()
            self.queue_tasks[voice_channel.id] = asyncio.create_task(self.process_queue(voice_channel.id))

        # 일반 작업이면 특수문자 처리: 텍스트에 영문/숫자/한글이 없으면 변환
        if job_type == "normal":
            processed_text = prepare_text(text)
        else:
            processed_text = text  

        # 에러 없이 빈 텍스트가 되지 않도록 방지 (빈 텍스트면 건너뜀)
        if processed_text.strip():
            await self.queues[voice_channel.id].put((job_type, processed_text))

    async def process_queue(self, channel_id):
        while True:
            job_type, text = await self.queues[channel_id].get()
            vc = self.voice_clients[channel_id]
            try:
                if job_type == "normal":
                    tts = gTTS(text=text, lang='ko')
                    tts.save('tts.mp3')
                    sound = AudioSegment.from_mp3('tts.mp3')
                    sound.export('tts.wav', format='wav')
                    vc.play(nextcord.FFmpegPCMAudio('tts.wav'))
                    while vc.is_playing():
                        await asyncio.sleep(0.5)
                elif job_type == "sans":
                    # Sans: 각 문자마다 SansSpeak.wav 재생
                    for char in text:
                        vc.play(nextcord.FFmpegPCMAudio('SansSpeak.wav'))
                        while vc.is_playing():
                            await asyncio.sleep(0.1)
                        if char.isspace():
                            await asyncio.sleep(0.5)
                        else:
                            await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error processing queue for channel {channel_id}: {e}")
            self.queues[channel_id].task_done()

    async def leave_empty_channels(self):
        for cid, vc in list(self.voice_clients.items()):
            if len(vc.channel.members) == 1:
                await vc.disconnect()
                del self.voice_clients[cid]
                if cid in self.queues:
                    self.queue_tasks[cid].cancel()
                    del self.queues[cid]
                    del self.queue_tasks[cid]

tts_player = TTSPlayer(bot)

##############################################
# /sans
@bot.slash_command(name='sans', description='Sans 기능: 입력한 텍스트의 글자 수만큼 SansSpeak.wav를 재생합니다.')
async def sans_command(interaction: Interaction, text: str = SlashOption(description="Sans 기능 실행할 텍스트")):
    target_guild = None
    target_member = None
    target_voice_channel = None

    if interaction.guild is None:
        # DM에서 호출된 경우: 봇이 가입한 서버들을 순회하며 사용자가 음성 채널에 접속해 있는 서버를 찾습니다.
        # 고쳐야함 
        # 아 싫다
        for guild in bot.guilds:
            member = guild.get_member(interaction.user.id)
            if member and member.voice and member.voice.channel:
                target_guild = guild
                target_member = member
                target_voice_channel = member.voice.channel
                break
        if target_guild is None:
            await interaction.response.send_message("음성 채널에 접속해 있는 서버를 찾을 수 없습니다.", ephemeral=True)
            return
    else:
        # 서버 내에서 호출된 경우
        target_guild = interaction.guild
        target_member = target_guild.get_member(interaction.user.id)
        if not target_member or not target_member.voice or not target_member.voice.channel:
            await interaction.response.send_message("음성 채널에 접속해 주세요!", ephemeral=True)
            return
        target_voice_channel = target_member.voice.channel

    # Sans을 대기열에 추가 (job_type "sans"로 처리)
    await tts_player.join_and_queue(text, target_voice_channel, job_type="sans")
    
    # # 해당 서버의 기본 텍스트 채널에 Sans 출력합니다.
    # default_text_channel = target_guild.text_channels[0] if target_guild.text_channels else None
    # if default_text_channel:
    #     await default_text_channel.send(f"{target_member.display_name}님의 Sans 명령: {text}")
        
    await interaction.response.send_message("✅ Sans 작업이 대기열에 추가되었습니다.", ephemeral=True)


##############################################
# on_message 이벤트 처리 (일반 TTS)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 서버 채널 처리
    if message.guild:
        settings = get_server_settings(message.guild.id)
        if settings["auto_tts"] and settings["chat_tts"]:
            voice_state = message.author.voice
            if voice_state and voice_state.channel:
                await tts_player.join_and_queue(message.content, voice_state.channel, job_type="normal")
        # 사용자가 보낸 메시지를 기본 텍스트 채널에도 출력 (이름 포함)
        # default_text_channel = message.guild.text_channels[0] if message.guild.text_channels else None
        # if default_text_channel:
        #     await default_text_channel.send(f"{message.author.display_name}: {message.content}")

    # DM 채널 처리
    elif isinstance(message.channel, nextcord.DMChannel):
        print(f"DM 받은 메시지: [{message.author.name}] {message.content}")
        for guild in bot.guilds:
            member = guild.get_member(message.author.id)
            if member and member.voice and member.voice.channel:
                settings = get_server_settings(guild.id)
                if settings["dm_tts"]:
                    await tts_player.join_and_queue(message.content, member.voice.channel, job_type="normal")
                break

    await bot.process_commands(message)

##############################################
# 주기적으로 빈 음성 채널 확인
# 개선 필요
@tasks.loop(minutes=1)
async def check_voice_channels():
    await tts_player.leave_empty_channels()

if not check_voice_channels.is_running():
    check_voice_channels.start()

##############################################
# 토큰 확인
def load_token_by_id(token_id: int, path='tokens.json'):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} 파일이 없습니다!")
    with open(path, 'r', encoding='utf-8') as f:
        tokens = json.load(f)
    token = tokens.get(str(token_id))
    if not token:
        raise ValueError(f"{token_id}번 토큰이 존재하지 않습니다.")
    return token



bot.run(load_token_by_id(1))