from aiogram.fsm.state import State, StatesGroup


class BoardCreateStates(StatesGroup):
    waiting_title = State()
    waiting_channel_id = State()


class AdminAddStates(StatesGroup):
    waiting_user_id = State()


class AdminRemoveStates(StatesGroup):
    waiting_user_id = State()


class UserBlockStates(StatesGroup):
    waiting_user_id = State()


class UserUnblockStates(StatesGroup):
    waiting_user_id = State()


class RateLimitStates(StatesGroup):
    waiting_board = State()
    waiting_seconds = State()
