import time

from sqlalchemy import delete, func, select, update

from . import connection
from .models import AutonomyAction, AutonomyState


async def get_autonomy_state():
    async with connection.SessionFactory() as session:
        return await session.get(AutonomyState, 1)


async def configure_autonomy(owner_id, guild_id, channel_id, goal, interval_minutes, allow_actions=False):
    async with connection.SessionFactory() as session:
        state = await session.get(AutonomyState, 1)
        if state is None:
            state = AutonomyState(id=1, revision=0)
            session.add(state)
        state.enabled = True
        state.allow_actions = allow_actions
        state.owner_id = owner_id
        state.guild_id = guild_id
        state.channel_id = channel_id
        state.goal = goal
        state.memory = ""
        state.interval_minutes = interval_minutes
        state.next_run_at = int(time.time())
        state.last_run_at = 0
        state.revision += 1
        await session.commit()
        return state


async def disable_autonomy():
    async with connection.SessionFactory() as session:
        await session.execute(
            update(AutonomyState).where(AutonomyState.id == 1)
            .values(enabled=False, revision=AutonomyState.revision + 1)
        )
        await session.commit()


async def claim_autonomy_run(now: int):
    async with connection.SessionFactory() as session:
        result = await session.execute(
            update(AutonomyState)
            .where(AutonomyState.id == 1, AutonomyState.enabled.is_(True), AutonomyState.next_run_at <= now)
            .values(last_run_at=now, next_run_at=now + AutonomyState.interval_minutes * 60)
            .returning(AutonomyState)
        )
        state = result.scalar_one_or_none()
        await session.commit()
        return state


async def autonomy_is_current(state) -> bool:
    current = await get_autonomy_state()
    return bool(current and current.enabled and current.revision == state.revision
                and current.owner_id == state.owner_id)


async def finish_autonomy_run(state, memory: str, wait_minutes: int):
    async with connection.SessionFactory() as session:
        await session.execute(
            update(AutonomyState)
            .where(AutonomyState.id == 1, AutonomyState.enabled.is_(True), AutonomyState.revision == state.revision)
            .values(memory=memory[:3000], next_run_at=int(time.time()) + wait_minutes * 60)
        )
        await session.commit()


async def get_autonomy_actions(limit: int = 10, owner_id: str | None = None, channel_id: str | None = None):
    async with connection.SessionFactory() as session:
        statement = select(AutonomyAction)
        if owner_id is not None:
            statement = statement.where(AutonomyAction.owner_id == owner_id)
        if channel_id is not None:
            statement = statement.where(AutonomyAction.channel_id == channel_id)
        result = await session.scalars(statement.order_by(AutonomyAction.id.desc()).limit(limit))
        return list(result)


async def reserve_autonomy_action(name: str, detail: str, signature: str | None = None, owner_id: str = "", channel_id: str = ""):
    now = int(time.time())
    async with connection.SessionFactory() as session:
        # Make the hourly budget check and reservation one SQLite write transaction.
        await session.execute(delete(AutonomyAction).where(AutonomyAction.created_at < now - 30 * 86400))
        if signature:
            duplicate = await session.scalar(select(AutonomyAction.id).where(
                AutonomyAction.signature == signature, AutonomyAction.created_at >= now - 86400,
            ).limit(1))
            used = await session.scalar(select(func.count()).select_from(AutonomyAction).where(
                AutonomyAction.signature.is_not(None), AutonomyAction.created_at >= now - 3600,
            ))
            if duplicate is not None or used >= 3:
                await session.commit()
                return None
        action = AutonomyAction(created_at=now, name=name, detail=detail[:1200], signature=signature,
                                owner_id=owner_id, channel_id=channel_id)
        session.add(action)
        await session.commit()
        return action.id


async def complete_autonomy_action(action_id: int, status: str):
    async with connection.SessionFactory() as session:
        await session.execute(update(AutonomyAction).where(AutonomyAction.id == action_id).values(status=status))
        await session.commit()
