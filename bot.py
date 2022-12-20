from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetMessagesRequest, GetHistoryRequest
from telethon.tl.functions.users import GetUsersRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon import TelegramClient, events
from tqdm import tqdm

import logging
import random
import time
import glob
import os
from datetime import datetime, timedelta, timezone

from settings import config
from database import orm


logging.basicConfig(
    level=logging.INFO,
    filename = "botlog.log",
    format = "%(asctime)s - %(module)s - %(levelname)s - %(funcName)s: %(lineno)d - %(message)s",
    datefmt='%H:%M:%S',
    )

bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage() 
dp = Dispatcher(bot, storage=storage)

client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
client.start()

'''Состояния'''

class ChatOpenLink(StatesGroup):
    waiting_link = State()

class ChatPrivateLink(StatesGroup):
    waiting_link = State()

class Mailing(StatesGroup):
    waiting_text = State()
    entity = State()

class AdminMailing(StatesGroup):
    waiting_text = State()
    entity = State()
    continue_mail = State()

class Support(StatesGroup):
    message = State()

class ListParsing(StatesGroup):
    waiting_links = State()

class ChatComments(StatesGroup):
    waiting_link = State()
    count_posts = State()

class ParsingActivity(StatesGroup):
    waiting_link = State()
    last_activity = State()

'''Команды'''

async def set_default_commands(dp):
    await dp.bot.set_my_commands(
        [
            types.BotCommand('start', 'Перезапустить бота'),
        ]
    )

'''Основное меню'''

@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    text = f'Привет *{message.from_user.first_name}*!\nЯ могу спарсить любой чат\nПросто нажми на кнопку *"Начать парсинг"* и следуй инструкциям 👇'
    response = orm.add_user(message.from_user.id, message.from_user.username)
    inline_markup = await main_menu()
    username = message.from_user.username
    count = 0
    if response == 1:
        users = orm.get_admins()
        for user in users:
            try:
                if message.from_user.username == None:
                    await bot.send_message(user.tg_id, text=f'Пользователь <a href="tg://user?id={message.from_user.id}">@{message.from_user.first_name}</a> присоединился', parse_mode='HTML')
                elif message.from_user.username != None:
                    await bot.send_message(user.tg_id, text=f'Пользователь <a href="tg://user?id={message.from_user.id}">@{username}</a> присоединился', parse_mode='HTML')
                else:
                   await bot.send_message(user.tg_id, text=f'Пользователь <a href="tg://user?id={message.from_user.id}">@{username}</a> присоединился', parse_mode='HTML') 
                count += 1
                if count == 10:
                    time.sleep(5)
                    count = 0
            except Exception as error:
                logging.error(error, exc_info=True)
    await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
    await set_default_commands(dp)

@dp.callback_query_handler(lambda call: 'main_menu' in call.data)
async def get_main_menu(callback_query: types.CallbackQuery):
    text = f'Привет *{callback_query.from_user.first_name}*!\nЯ могу спарсить любой чат\nПросто нажми на кнопку *"Начать парсинг"* и следуй инструкциям 👇'
    inline_markup = await main_menu()
    await callback_query.message.edit_text(text, reply_markup=inline_markup, parse_mode='Markdown')

'''Обработка нажатий основного меню'''

@dp.callback_query_handler(lambda call: 'premium_menu' in call.data)
async def get_premium_menu(callback_query: types.CallbackQuery):
    text = 'Выберите необходимый вариант из списка'
    inline_markup = await premium_menu()
    await callback_query.message.edit_text(text, reply_markup=inline_markup, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'support' in call.data)
async def create_support_message(callback_query: types.CallbackQuery):
    text = 'Опишите свою проблему в *ОДНОМ* сообщении и отправте его мне, я передам его администраторам'
    await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
    await Support.message.set()

@dp.callback_query_handler(lambda call: 'parsing_open_start' in call.data)
async def parsing_open_start(callback_query: types.CallbackQuery):
    text = 'Отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
    await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
    await ChatOpenLink.waiting_link.set()

'''Обработка нажатий премиум меню'''

@dp.callback_query_handler(lambda call: 'parsing_list_start' in call.data)
async def parsing_list_start(callback_query: types.CallbackQuery):
    if orm.check_premium(callback_query.from_user.id) == 1:
        text = 'Введите список чатов (как открытых так и приватных), чаты необходимо вводить в столбик (SHIFT+Enter).\nНапиример:\n*t.mе/durоv*\n*@durоv*\n*t.mе/durоv*'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
        await ListParsing.waiting_links.set()
    else:
        text = 'Данная функция доступна только премиум пользователям'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'parsing_private_start' in call.data)
async def parsing_private_start(callback_query: types.CallbackQuery):
    text = f'Выберите необходимую функцию'
    inline_markup = await premium_parsing_menu()
    await callback_query.message.edit_text(text, reply_markup=inline_markup, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'private_all' in call.data)
async def parsing_all_start(callback_query: types.CallbackQuery):
    if orm.check_premium(callback_query.from_user.id) == 1:
        text = 'Отправьте ссылку на приватный чат в формате:\n*https://t.me/abc123* либо *https://t.me/joinchat/abc123*'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
        await ChatPrivateLink.waiting_link.set()
    else:
        text = 'Данная функция доступна только премиум пользователям'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'parsing_comments' in call.data)
async def parsing_comments_start(callback_query: types.CallbackQuery):
    if orm.check_premium(callback_query.from_user.id) == 1:
        text = 'Отправьте ссылку на канал *в котором есть комментарии* и я выдам всех пользователей писавших комментарии'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
        await ChatComments.waiting_link.set()
    else:
        text = 'Данная функция доступна только премиум пользователям'
        await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'parsing_activity' in call.data)
async def parsing_activity_start(callback_query: types.CallbackQuery):
    text = 'Отправьте ссылку на чат'
    await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')
    await ParsingActivity.waiting_link.set()

@dp.message_handler(state=ParsingActivity.waiting_link)
async def get_private_report(message: types.Message, state: FSMContext):
    await state.update_data(waiting_link=message.text)
    inline_markup = await activity_menu()
    text = 'За какой промежуток времени пользователи должны были быть онлайн?'
    await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
    await ParsingActivity.last_activity.set()

'''Админка и все действия с ней'''

@dp.message_handler(lambda message: orm.check_admin(message.from_user.id) == 1 and message.text == '/admin')
async def get_admin_menu(message: types.Message):
    text = 'Выберите необходимое действие'
    inline_markup = await admin_menu()
    await message.answer(text, reply_markup=inline_markup)

@dp.callback_query_handler(lambda call: 'stat' in call.data)
async def get_stat(callback_query: types.CallbackQuery):
    stat = orm.get_stat()
    text = f'Всего пользователей: {stat[0]}\nУдалили чат с ботом: {stat[1]}\n*Количество удаливших чат с ботом обновляется после рассылки*'
    await bot.send_message(callback_query.from_user.id, text, parse_mode='Markdown')

@dp.callback_query_handler(lambda call: 'create_admin_mailing' in call.data)
async def start_admin_mailing(callback_query: types.CallbackQuery):
    text = 'Напишите сообщение, которое вы хотите разослать'
    await bot.send_message(callback_query.from_user.id, text)
    await AdminMailing.waiting_text.set()

@dp.message_handler(state=AdminMailing.waiting_text)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(waiting_text=message.text, entity=message.entities)
    state_data = await state.get_data()
    text = state_data.get('waiting_text')
    entity = state_data.get('entity')
    users = orm.get_admins()
    answer = 'Начинаю рассылку'
    await message.answer(answer, parse_mode='Markdown')
    count = 0
    count_of_users = len(users)
    count_of_banned = 0
    for user in users:
        try:
            await bot.send_message(user.tg_id, text=text, entities=entity, disable_web_page_preview=True)
            count += 1
            if count == 10:
                    time.sleep(5)
                    count = 0
        except Exception as error:
            logging.error(error, exc_info=True)
            count_of_banned += 1
    answer1 = f'Отправка рыссылки завершена\nВсего админов: {count_of_users}\nОтправлено успешно: {count_of_users-count_of_banned}\nУдалили чат с ботом: {count_of_banned}'
    await message.answer(answer1, parse_mode='Markdown')
    answer2 = 'Разослать всем?'
    await message.answer(answer2, parse_mode='Markdown')
    await AdminMailing.continue_mail.set()

@dp.message_handler(state=AdminMailing.continue_mail)
async def mailing_all_users(message: types.Message, state: FSMContext):
    await state.update_data(continue_mail=message.text)
    state_data = await state.get_data()
    answer = state_data.get('continue_mail')
    text = state_data.get('waiting_text')
    entity = state_data.get('entity')
    if answer.upper() == 'ДА':
        users = orm.get_all_users()
        answer1 = 'Начинаю рассылку'
        await message.answer(answer1, parse_mode='Markdown')
        count = 0
        count_of_users = len(users)
        count_of_banned = 0
        for user in users:
            try:
                await bot.send_message(user.tg_id, text=text, entities=entity, disable_web_page_preview=True)
                count += 1
                if orm.check_blocked(user.tg_id) == -1:
                    orm.delete_from_blocked(user.tg_id)
                if count == 10:
                    time.sleep(5)
                    count = 0
            except Exception as error:
                count_of_banned += 1
                orm.add_blocked_users(user.tg_id, user.username)
        answer2 = f'Отправка рыссылки завершена\nВсего пользователей: {count_of_users}\nОтправлено успешно: {count_of_users-count_of_banned}\nУдалили чат с ботом: {count_of_banned}'
        await message.answer(answer2, parse_mode='Markdown')
        await state.finish()
    else:
        answer1 = 'Отправка рассылки отменена'
        await message.answer(answer2, parse_mode='Markdown')
        await state.finish()

@dp.callback_query_handler(lambda call: 'create_mailing' in call.data)
async def start_mailing(callback_query: types.CallbackQuery):
    text = 'Напишите сообщение, которое вы хотите разослать'
    await bot.send_message(callback_query.from_user.id, text)
    await Mailing.waiting_text.set()

@dp.message_handler(state=Mailing.waiting_text)
async def get_mailing_text(message: types.Message, state: FSMContext):
    await state.update_data(waiting_text=message.text, entity=message.entities)
    state_data = await state.get_data()
    text = state_data.get('waiting_text')
    entity = state_data.get('entity')
    users = orm.get_all_users()
    answer = 'Начинаю рассылку'
    await message.answer(answer, parse_mode='Markdown')
    count = 0
    count_of_users = len(users)
    count_of_banned = 0
    for user in users:
        try:
            await bot.send_message(user.tg_id, text=text, entities=entity, disable_web_page_preview=True)
            count += 1
            if orm.check_blocked(user.tg_id) == -1:
                    orm.delete_from_blocked(user.tg_id)
            if count == 10:
                    time.sleep(5)
                    count = 0
        except Exception as error:
            orm.add_blocked_users(user.tg_id, user.username)
            count_of_banned += 1
    answer1 = f'Отправка рыссылки завершена\nВсего пользователей: {count_of_users}\nОтправлено успешно: {count_of_users-count_of_banned}\nУдалили чат с ботом: {count_of_banned}'
    await message.answer(answer1, parse_mode='Markdown')
    await state.finish()

'''Тех поддержка'''

@dp.message_handler(state=Support.message)
async def send_support_message(message: types.Message, state: FSMContext):
    await state.update_data(message=message.text)
    state_data = await state.get_data()
    text = state_data.get('message')
    answer = 'Ваше сообщение отправлено в техническую поддержку, ответ получите в этом чате после рассмотрения заявки'
    await bot.forward_message(chat_id=-830939578, from_chat_id=message.chat.id, message_id=message.message_id)
    await message.answer(answer)
    await state.finish()

@client.on(events.NewMessage(chats=(-830939578)))
async def create_support_msg(event):
    msg = event.message.to_dict()
    text = msg['message']
    msg_id = msg['reply_to']['reply_to_msg_id']
    result = await client(GetMessagesRequest(id=[msg_id]))
    user = result.messages[0].fwd_from.from_id.user_id
    await bot.send_message(user, text)

'''Парсинг для премиум пользователей'''

@dp.message_handler(state=ChatPrivateLink.waiting_link)
async def get_private_report(message: types.Message, state: FSMContext):
    await state.update_data(waiting_link=message.text)
    if '@' not in message.text and 't.me' not in message.text:
        text = 'Введена неверная ссылка на чат, выберите необходимое действие'
        inline_markup = await premium_menu()
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        await state.finish()
    state_data = await state.get_data()
    link = state_data.get('waiting_link')
    if 'joinchat' in link:
        hash = link[link.index('chat')+5:]
    elif '+' in link:
        hash = link[link.index('+')+1:]
    else:
        hash = link
    try:
        await client(ImportChatInviteRequest(hash))
        channel = await client.get_entity(link)
        queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
        LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
        ALL_PARTICIPANTS = []  # Список всех участников канала
        await message.answer(text='Начинаю парсинг, это может занять от 10 до 15 минут⏱')
        for key in queryKey:
            if queryKey.index(key) == 12:
                await message.answer(text='50% завершено')
            print(f'{queryKey.index(key)+1}/{len(queryKey)}')
            OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
            while True:
                participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                if not participants.users:
                    break
                ALL_PARTICIPANTS.extend(participants.users)
                OFFSET_USER += len(participants.users)
            target = '*.txt'
            file = glob.glob(target)[0]
            with open(file, "w", encoding="utf-8") as write_file:
                for participant in tqdm(ALL_PARTICIPANTS):
                    try:
                        if participant.username != None and participant.bot == False and participant.fake == False:
                            write_file.writelines(f"@{participant.username}\n")
                    except Exception as error:  
                        logging.error(error, exc_info=True)
        target = '*.txt'
        file = glob.glob(target)[0]
        os.rename(file, f'{channel.title}.txt')
        file = glob.glob(target)[0]
        uniqlines = set(open(file,'r', encoding='utf-8').readlines())
        open(file,'w', encoding='utf-8').writelines(set(uniqlines))
        with open(file, "r+", encoding="utf-8") as write_file:
            lines = write_file.readlines()
            top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
            lines[0] = top_text
            write_file.seek(0)
            write_file.writelines(lines)
        await state.finish()
        text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
        inline_markup = await premium_menu()
        await message.reply_document(open(file, 'rb'))
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
    except Exception as error:
        if 'The authenticated user is already a participant' in error.args[0]:
            channel = await client.get_entity(link)
            queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
            LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
            ALL_PARTICIPANTS = []  # Список всех участников канала
            for key in queryKey:
                if queryKey.index(key) == 12:
                    await message.answer(text='50% завершено')
                print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                while True:
                    participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                    if not participants.users:
                        break
                    ALL_PARTICIPANTS.extend(participants.users)
                    OFFSET_USER += len(participants.users)
                target = '*.txt'
                file = glob.glob(target)[0]
                with open(file, "w", encoding="utf-8") as write_file:
                    for participant in tqdm(ALL_PARTICIPANTS):
                        try:
                            if participant.username != None and participant.bot == False and participant.fake == False:
                                write_file.writelines(f"@{participant.username}\n")
                        except Exception as error:  
                            logging.error(error, exc_info=True)
            target = '*.txt'
            file = glob.glob(target)[0]
            os.rename(file, f'{channel.title}.txt')
            file = glob.glob(target)[0]
            uniqlines = set(open(file,'r', encoding='utf-8').readlines())
            open(file,'w', encoding='utf-8').writelines(set(uniqlines))
            await state.finish()
            text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
            inline_markup = await premium_menu()
            await message.reply_document(open(file, 'rb'))
            await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        if 'The chat the user tried to join has expired and is not valid anymore' in error.args[0]:
            text = 'Эта пригласительная ссылка недействительна или устарела, снова нажмите кнопку "Начать парсинг"'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'The API access for bot users is restricted.' in error.args[0]:
            text = 'Данный функционал ещё не реализован, снова нажмите кнопку "Начать парсинг"'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        logging.error(error, exc_info=True)
        if 'Cannot find any entity corresponding' in error.args[0] or 'Nobody is using this username' in error.args[0]:
            text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг"'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'No user has' in error.args[0]:
            text = 'Такого чата не существует, нажмите кнопку "Начать парсинг"'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'Cannot cast InputPeerUser' in error.args[0]:
            text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг"'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        await state.finish()

@dp.message_handler(state=ListParsing.waiting_links)
async def get_list_report(message: types.Message, state: FSMContext):
    await state.update_data(waiting_links=message.text)
    state_data = await state.get_data()
    list_of_links = state_data.get('waiting_links').split('\n')
    inline_markup = await premium_menu()
    for link in list_of_links:
        if '@' not in message.text and 't.me' not in message.text:
            text = f'{link}\nВведена неверная ссылка на чат, ссылка обязательно должна в себе содержать @ или t.me'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
            await state.finish()
    text = 'Начинаю парсинг, это может занять довольно много времени (зависит от количества чатов и числа их участников)'
    await message.answer(text, parse_mode='Markdown')
    ALL_PARTICIPANTS = []
    for link in list_of_links:
        if 'joinchat' not in link and '+' not in link:
            try:
                channel = await client.get_entity(link)
                queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
                LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
                for key in queryKey:
                    print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                    OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                    while True:
                        participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                        if not participants.users:
                            break
                        ALL_PARTICIPANTS.extend(participants.users)
                        OFFSET_USER += len(participants.users)
            except Exception as error:
                pass
        if 'joinchat' in link or '+' in link:
            if 'joinchat' in link:
                hash = link[link.index('chat')+5:]
            else:
                hash = link[link.index('+')+1:]
            try:
                await client(ImportChatInviteRequest(hash))
                channel = await client.get_entity(link)
                queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
                LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
                for key in queryKey:
                    print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                    OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                    while True:
                        participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                        if not participants.users:
                            break
                        ALL_PARTICIPANTS.extend(participants.users)
                        OFFSET_USER += len(participants.users)
                        print(len(ALL_PARTICIPANTS))
            except Exception as error:
                if 'The authenticated user is already a participant' in error.args[0]:
                    channel = await client.get_entity(link)
                    queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
                    LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
                    for key in queryKey:
                        print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                        OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                        while True:
                            participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                            if not participants.users:
                                break
                            ALL_PARTICIPANTS.extend(participants.users)
                            OFFSET_USER += len(participants.users)
    target = '*.txt'
    file = glob.glob(target)[0]
    with open(file, "w", encoding="utf-8") as write_file:
        for participant in tqdm(ALL_PARTICIPANTS):
            if participant.username != None and participant.bot == False and participant.fake == False:
                write_file.writelines(f"@{participant.username}\n")
    os.rename(file, 'report.txt')
    file = glob.glob(target)[0]
    uniqlines = set(open(file,'r', encoding='utf-8').readlines())
    open(file,'w', encoding='utf-8').writelines(set(uniqlines))
    with open(file, "r+", encoding="utf-8") as write_file:
        lines = write_file.readlines()
        top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
        lines[0] = top_text
        write_file.seek(0)
        write_file.writelines(lines)
    await state.finish()
    text = 'Выберите необходимое действие'
    inline_markup = await premium_menu()
    await message.reply_document(open(file, 'rb'))
    await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')

@dp.message_handler(state=ChatComments.waiting_link)
async def get_discussion_users(message: types.Message, state: FSMContext):
    try:
        await state.update_data(waiting_link=message.text)
        if '@' not in message.text and 't.me' not in message.text:
            text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат *t.mе/durov* или *@durоv*'
            inline_markup = await premium_menu()
            await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
            await state.finish()
            return
        await message.answer(text='Теперь введите количество последних постов для парсинга (не более 100)')
        await ChatComments.count_posts.set()
    except Exception as error:
        text = 'Ссылка больше не действительна'
        inline_markup = await main_menu()
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        await state.finish()

@dp.message_handler(state=ChatComments.count_posts)
async def get_comments_users(message: types.Message, state: FSMContext):
    try:
        await state.update_data(count_posts=message.text)
        state_data = await state.get_data()
        state_data = await state.get_data()
        link = state_data.get('waiting_link')
        count = int(state_data.get('count_posts'))
        if 'joinchat' in link:
            hash = link[link.index('chat')+5:]
        elif '+' in link:
            hash = link[link.index('+')+1:]
        else:
            hash = link
        try:
            await client(ImportChatInviteRequest(hash))
            channel = await client.get_entity(link)
            ALL_USERS = []  # Список всех участников канала
            await message.answer(text='Начинаю парсинг, это может занять от 10 до 15 минут⏱')
            posts = await client(GetHistoryRequest(peer=channel,limit=count,offset_date=None,offset_id=0,max_id=0,min_id=0,add_offset=0,hash=0))
            for post in posts.messages:
                try:
                    async for msg in client.iter_messages(channel.id, reply_to=post.id):
                        ALL_USERS.append(msg.sender)
                except Exception as error:
                    pass
            target = '*.txt'
            file = glob.glob(target)[0]
            with open(file, "w", encoding="utf-8") as write_file:
                for user in tqdm(ALL_USERS):
                    try:
                        if user.username != None and user.bot == False and user.fake == False:
                            write_file.writelines(f"@{user.username}\n")
                    except Exception as error:  
                        pass
            target = '*.txt'
            file = glob.glob(target)[0]
            os.rename(file, f'Комментарии {channel.title}.txt')
            file = glob.glob(target)[0]
            uniqlines = set(open(file,'r', encoding='utf-8').readlines())
            open(file,'w', encoding='utf-8').writelines(set(uniqlines))
            with open(file, "r+", encoding="utf-8") as write_file:
                lines = write_file.readlines()
                top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                lines[0] = top_text
                write_file.seek(0)
                write_file.writelines(lines)
            await state.finish()
            text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
            inline_markup = await premium_menu()
            await message.reply_document(open(file, 'rb'))
            await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        except Exception as error:
            if 'The authenticated user is already a participant' in error.args[0]:
                channel = await client.get_entity(link)
                ALL_USERS = []  # Список всех участников канала
                await message.answer(text='Начинаю парсинг, это может занять от 10 до 15 минут⏱')
                posts = await client(GetHistoryRequest(peer=channel,limit=count,offset_date=None,offset_id=0,max_id=0,min_id=0,add_offset=0,hash=0))
                for post in posts.messages:
                    try:
                        async for msg in client.iter_messages(channel.id, reply_to=post.id):
                            ALL_USERS.append(msg.sender)
                    except Exception as error:
                        pass
                target = '*.txt'
                file = glob.glob(target)[0]
                top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n\# Группы: {channel.title}o\n# Собрано: {datetime.now()}\n-------------------------------------'
                with open(file, "w", encoding="utf-8") as write_file:
                    write_file.writelines(top_text)
                    for user in tqdm(ALL_USERS):
                        try:
                            if user.username != None and user.bot == False and user.fake == False:
                                write_file.writelines(f"@{user.username}\n")
                        except Exception as error:  
                            pass
                target = '*.txt'
                file = glob.glob(target)[0]
                os.rename(file, f'Комментарии {channel.title}.txt')
                file = glob.glob(target)[0]
                uniqlines = set(open(file,'r', encoding='utf-8').readlines())
                open(file,'w', encoding='utf-8').writelines(set(uniqlines))
                with open(file, "r+", encoding="utf-8") as write_file:
                    lines = write_file.readlines()
                    top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                    lines[0] = top_text
                    write_file.seek(0)
                    write_file.writelines(lines)
                await state.finish()
                text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
                inline_markup = await premium_menu()
                await message.reply_document(open(file, 'rb'))
                await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
            if 'The chat the user tried to join has expired and is not valid anymore' in error.args[0]:
                try:
                    channel = await client.get_entity(link)
                    ALL_USERS = []  # Список всех участников канала
                    await message.answer(text='Начинаю парсинг, это может занять от 10 до 15 минут⏱')
                    posts = await client(GetHistoryRequest(peer=channel,limit=count,offset_date=None,offset_id=0,max_id=0,min_id=0,add_offset=0,hash=0))
                    for post in posts.messages:
                        try:
                            async for msg in client.iter_messages(channel.id, reply_to=post.id):
                                ALL_USERS.append(msg.sender)
                        except Exception as error:
                            pass
                    target = '*.txt'
                    file = glob.glob(target)[0]
                    with open(file, "w", encoding="utf-8") as write_file:
                        for user in tqdm(ALL_USERS):
                            try:
                                if user.username != None and user.bot == False and user.fake == False:
                                    write_file.writelines(f"@{user.username}\n")
                            except Exception as error:  
                                pass
                    target = '*.txt'
                    file = glob.glob(target)[0]
                    os.rename(file, f'Комментарии {channel.title}.txt')
                    file = glob.glob(target)[0]
                    uniqlines = set(open(file,'r', encoding='utf-8').readlines())
                    open(file,'w', encoding='utf-8').writelines(set(uniqlines))
                    with open(file, "r+", encoding="utf-8") as write_file:
                        lines = write_file.readlines()
                        top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                        lines[0] = top_text
                        write_file.seek(0)
                        write_file.writelines(lines)
                    await state.finish()
                    text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
                    inline_markup = await premium_menu()
                    await message.reply_document(open(file, 'rb'))
                    await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
                except Exception as error:
                    text = 'Ссылка больше не действительна'
                    inline_markup = await main_menu()
                    await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
                    await state.finish()
    except Exception as error:
        text = 'Ссылка больше не действительна'
        inline_markup = await main_menu()
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        await state.finish()

@dp.callback_query_handler(state=ParsingActivity.last_activity)
async def parsing_activity_start(callback_query: types.CallbackQuery, state: FSMContext):
    if orm.check_premium(callback_query.from_user.id) == -1:
        text = 'Данная функция доступна только премиум пользователям'
        inline_markup = await premium_parsing_menu()
        await bot.send_message(callback_query.from_user.id, text, reply_markup=inline_markup, parse_mode='Markdown')
        await state.finish()
    else: 
        await state.update_data(last_activity=callback_query.data)
        state_data = await state.get_data()
        link = state_data.get('waiting_link')
        online = state_data.get('last_activity').split('_')[1]
        hours = int(online)
        await bot.send_message(callback_query.from_user.id, text='Начинаю парсинг, это может занять от 10 до 15 минут⏱', parse_mode='Markdown')
    if 'joinchat' not in link and '+' not in link:
            ALL_PARTICIPANTS = []
            channel = await client.get_entity(link)
            queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
            LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
            for key in queryKey:
                if queryKey.index(key) == 12:
                    await bot.send_message(callback_query.from_user.id, text='50% завершено')
                print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                while True:
                    participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                    if not participants.users:
                        break
                    ALL_PARTICIPANTS.extend(participants.users)
                    OFFSET_USER += len(participants.users)
            ALL_PARTICIPANTS = await sort_by_activity(ALL_PARTICIPANTS, hours)
            target = '*.txt'
            file = glob.glob(target)[0]
            with open(file, "w", encoding="utf-8") as write_file:
                for participant in tqdm(ALL_PARTICIPANTS):
                        if participant.username != None and participant.bot == False and participant.fake == False:
                            write_file.writelines(f"@{participant.username}\n")
            target = '*.txt'
            file = glob.glob(target)[0]
            os.rename(file, f'{channel.title}.txt')
            file = glob.glob(target)[0]
            uniqlines = set(open(file,'r', encoding='utf-8').readlines())
            open(file,'w', encoding='utf-8').writelines(set(uniqlines))
            with open(file, "r+", encoding="utf-8") as write_file:
                lines = write_file.readlines()
                top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                lines[0] = top_text
                write_file.seek(0)
                write_file.writelines(lines)
            await state.finish()
            text = 'Для парсинга следующего чата выберите необходимое действие'
            inline_markup = await premium_menu()
            await bot.send_document(callback_query.from_user.id, open(file, 'rb'))
            await bot.send_message(callback_query.from_user.id, text, reply_markup=inline_markup)
    if 'joinchat' in link or '+' in link:
            if 'joinchat' in link:
                hash = link[link.index('chat')+5:]
            else:
                hash = link[link.index('+')+1:]
            try:
                ALL_PARTICIPANTS = []
                await client(ImportChatInviteRequest(hash))
                channel = await client.get_entity(link)
                queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
                LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
                for key in queryKey:
                    if queryKey.index(key) == 12:
                        await bot.send_message(callback_query.from_user.id, text='50% завершено')
                    print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                    OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                    while True:
                        participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                        if not participants.users:
                            break
                        ALL_PARTICIPANTS.extend(participants.users)
                        OFFSET_USER += len(participants.users)
                ALL_PARTICIPANTS = await sort_by_activity(ALL_PARTICIPANTS, hours)
                target = '*.txt'
                file = glob.glob(target)[0]
                with open(file, "w", encoding="utf-8") as write_file:
                    for participant in tqdm(ALL_PARTICIPANTS):
                            if participant.username != None and participant.bot == False and participant.fake == False:
                                write_file.writelines(f"@{participant.username}\n")
                target = '*.txt'
                file = glob.glob(target)[0]
                os.rename(file, f'{channel.title}.txt')
                file = glob.glob(target)[0]
                uniqlines = set(open(file,'r', encoding='utf-8').readlines())
                open(file,'w', encoding='utf-8').writelines(set(uniqlines))
                with open(file, "r+", encoding="utf-8") as write_file:
                    lines = write_file.readlines()
                    top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                    lines[0] = top_text
                    write_file.seek(0)
                    write_file.writelines(lines)
                await state.finish()
                text = 'Для парсинга следующего чата выберите необходимое действие'
                inline_markup = await premium_menu()
                await bot.send_document(callback_query.from_user.id, open(file, 'rb'))
                await bot.send_message(callback_query.from_user.id, text, reply_markup=inline_markup)
            except Exception as error:
                if 'The authenticated user is already a participant' in error.args[0]:
                    ALL_PARTICIPANTS = []
                    channel = await client.get_entity(link)
                    queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                        'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                        'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
                    LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
                    for key in queryKey:
                        if queryKey.index(key) == 12:
                            await bot.send_message(callback_query.from_user.id, text='50% завершено')
                        print(f'{queryKey.index(key)+1}/{len(queryKey)}')
                        OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
                        while True:
                            participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                            if not participants.users:
                                break
                            ALL_PARTICIPANTS.extend(participants.users)
                            OFFSET_USER += len(participants.users)
                    ALL_PARTICIPANTS = await sort_by_activity(ALL_PARTICIPANTS, hours)
                    target = '*.txt'
                    file = glob.glob(target)[0]
                    with open(file, "w", encoding="utf-8") as write_file:
                        for participant in tqdm(ALL_PARTICIPANTS):
                                if participant.username != None and participant.bot == False and participant.fake == False:
                                    write_file.writelines(f"@{participant.username}\n")
                    target = '*.txt'
                    file = glob.glob(target)[0]
                    os.rename(file, f'{channel.title}.txt')
                    file = glob.glob(target)[0]
                    uniqlines = set(open(file,'r', encoding='utf-8').readlines())
                    open(file,'w', encoding='utf-8').writelines(set(uniqlines))
                    with open(file, "r+", encoding="utf-8") as write_file:
                        lines = write_file.readlines()
                        top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
                        lines[0] = top_text
                        write_file.seek(0)
                        write_file.writelines(lines)
                    await state.finish()
                    text = 'Для парсинга следующего чата выберите необходимое действие'
                    inline_markup = await premium_menu()
                    await bot.send_document(callback_query.from_user.id, open(file, 'rb'))
                    await bot.send_message(callback_query.from_user.id, text, reply_markup=inline_markup)
    
'''Парсинг для обычных пользователей'''

@dp.message_handler(state=ChatOpenLink.waiting_link)
async def get_open_report(message: types.Message, state: FSMContext):
    await state.update_data(waiting_link=message.text)
    if '@' not in message.text and 't.me' not in message.text:
        text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат *t.mе/durov* или *@durоv*'
        inline_markup = await main_menu()
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
        await state.finish()
    state_data = await state.get_data()
    link = state_data.get('waiting_link')
    try:
        channel = await client.get_entity(link)
        queryKey = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 
                'u', 'v', 'w', 'x', 'y', 'z'] # Латинский алфавит на каждую букву которого делается запрос
        LIMIT_USER = 200  # Максимальное число записей, передаваемых за один раз, не более 200
        ALL_PARTICIPANTS = []  # Список всех участников канала
        await message.answer(text='Начинаю парсинг, это может занять от 10 до 15 минут⏱')
        for key in queryKey:
            if queryKey.index(key) == 13:
                await message.answer(text='50% завершено')
            print(f'{queryKey.index(key)+1}/{len(queryKey)}')
            OFFSET_USER = 0 # номер пользователя, с которого начинается считывание
            while True:
                participants = await client(GetParticipantsRequest(channel,ChannelParticipantsSearch(key), OFFSET_USER, LIMIT_USER, hash=0))
                if not participants.users:
                    break
                ALL_PARTICIPANTS.extend(participants.users)
                OFFSET_USER += len(participants.users)
            target = '*.txt'
            file = glob.glob(target)[0] 
            with open(file, "w", encoding="utf-8") as write_file:
                for participant in tqdm(ALL_PARTICIPANTS):
                    try:
                        if participant.username != None and participant.bot == False and participant.fake == False:
                            write_file.writelines(f"@{participant.username}\n")
                    except Exception as error:  
                        logging.error(error, exc_info=True)
        target = '*.txt'
        file = glob.glob(target)[0]
        os.rename(file, f'{channel.title}.txt')
        file = glob.glob(target)[0]
        uniqlines = set(open(file,'r', encoding='utf-8').readlines())
        open(file,'w', encoding='utf-8').writelines(set(uniqlines))
        with open(file, "r+", encoding="utf-8") as write_file:
            lines = write_file.readlines()
            top_text = f'-------------------------------------\n# Сбор через бота: {dp.bot._me.mention}\n# Группы: {channel.title}\n# Собрано: {datetime.now()}\n# Количество строк: {len(lines)+5}\n-------------------------------------\n'
            lines[0] = top_text
            write_file.seek(0)
            write_file.writelines(lines)
        await state.finish()
        text = 'Для парсинга следующего чата нажмите кнопку "Начать парсинг" и отправьте ссылку на ваш чат в формате *t.mе/durоv* или *@durоv*'
        inline_markup = await main_menu()
        await message.reply_document(open(file, 'rb'))
        await message.answer(text, reply_markup=inline_markup, parse_mode='Markdown')
    except Exception as error:
        if 'Invalid channel object' in error.args[0]:
            text = 'Пасринг приватных чатов доступен только премиум пользователям'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        logging.error(error, exc_info=True)
        if 'Cannot find any entity corresponding' in error.args[0] or 'Nobody is using this username' in error.args[0]:
            text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг"'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'No user has' in error.args[0]:
            text = 'Такого чата не существует, нажмите кнопку "Начать парсинг"'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'Cannot cast InputPeerUser' in error.args[0]:
            text = 'Введена неверная ссылка на чат, нажмите кнопку "Начать парсинг"'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'Cannot get entity from a channel (or group)' in error.args[0]:
            text = 'Это приватный чат, приобретите премиум статус для парсинга чатов такого рода'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        if 'Chat admin privileges are required to do that in the specified chat' in error.args[0]:
            text = 'Это приватный чат, приобретите премиум статус для парсинга чатов такого рода'
            inline_markup = await main_menu()
            await message.answer(text, reply_markup=inline_markup)
            await state.finish()
        await state.finish()
   
'''Шаблоны всех меню'''
    
async def main_menu():
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton(
            text='🔍Спарсить открытый чат', 
            callback_data='parsing_open_start'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='🔒Premium функции', 
            callback_data='premium_menu'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='🔧Написать в поддержку', 
            callback_data='support'
        ))
    return inline_markup

async def premium_menu():
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton(
        text='Парсинг открытого/приватного чата', 
        callback_data='parsing_private_start'
    ))
    inline_markup.add(types.InlineKeyboardButton(
            text='Спарсить чаты списком', 
            callback_data='parsing_list_start'
    ))
    inline_markup.add(types.InlineKeyboardButton(
            text='🔙Назад', 
            callback_data='main_menu'
        ))
    return inline_markup

async def admin_menu():
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton(
            text='Создать рассылку', 
            callback_data='create_mailing'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='Создать тестовую рассылку', 
            callback_data='create_admin_mailing'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='Статистика', 
            callback_data='stat'
        ))
    return inline_markup

async def premium_parsing_menu():
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton(
            text='Собрать всех', 
            callback_data='private_all'
    ))
    inline_markup.add(types.InlineKeyboardButton(
            text='По дате последнего посещения', 
            callback_data='parsing_activity'
    ))
    inline_markup.add(types.InlineKeyboardButton(
        text='Из комментариев к постам', 
        callback_data='parsing_comments'
    ))
    inline_markup.add(types.InlineKeyboardButton(
        text='Отмена', 
        callback_data='premium_menu'
    ))
    return inline_markup

async def activity_menu():
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton(
            text='За 1 час', 
            callback_data='online_1'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='За 6 часов', 
            callback_data='online_6'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='За сутки', 
            callback_data='online_24'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='За 3 дня', 
            callback_data='online_72'
        ))
    inline_markup.add(types.InlineKeyboardButton(
            text='За 7 дней', 
            callback_data='online_168'
        ))
    inline_markup.add(types.InlineKeyboardButton(
        text='Отмена', 
        callback_data='parsing_private_start'
    ))
    return inline_markup

'''Сортировка по последней активности'''

async def sort_by_activity(all_particapants, hours):
    current_time_utc =  datetime.now(timezone.utc)
    target_time = current_time_utc - timedelta(hours=hours, minutes=0)
    list_id = []
    for user in all_particapants:
        list_id.append(user.id)
    finish_list = await client(GetUsersRequest(list_id))
    for participant in finish_list:
        try:
            if participant.status.was_online > target_time:
                continue
            if participant.status.was_online < target_time:
                finish_list.remove(participant)
        except Exception as error:
            finish_list.remove(participant)
    return finish_list


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
    with client:
        client.loop.run_until_complete()