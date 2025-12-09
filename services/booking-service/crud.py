from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import models
import schemas
from config import settings
from timezone_utils import now_msk, msk_to_utc
from notifications import (
    get_user_email, 
    send_email_notification, 
    send_push_notification,
    notify_booking_created,
    notify_booking_cancelled,
    notify_booking_extended,
    notify_zone_closed
)

# ============================================================
#                       READ-ONLY ЧАСТЬ
# ============================================================

async def get_zones(session: AsyncSession, include_inactive: bool = False) -> List[schemas.ZoneOut]:
    now = msk_to_utc(now_msk())
    stmt_reactivate = (
        select(models.Zone)
        .where(
            and_(
                models.Zone.is_active.is_(False),
                models.Zone.closed_until.isnot(None),
                models.Zone.closed_until <= now,
            )
        )
    )
    result = await session.execute(stmt_reactivate)
    zones_to_reactivate = list(result.scalars().all())
    
    for zone in zones_to_reactivate:
        zone.is_active = True
        zone.closure_reason = None
        zone.closed_until = None
    
    if zones_to_reactivate:
        await session.commit()
    
    if include_inactive:
        stmt = select(models.Zone).order_by(models.Zone.name)
    else:
        stmt = (
            select(models.Zone)
            .where(models.Zone.is_active.is_(True))
            .order_by(models.Zone.name)
        )
    result = await session.execute(stmt)
    zones: List[models.Zone] = list(result.scalars().all())

    all_zone_ids = [zone.id for zone in zones]

    stmt_stats = (
        select(
            models.Zone.id.label('zone_id'),
            func.count(case((models.Booking.status == "active", 1))).label("active_bookings"),
            func.count(case((models.Booking.status == "cancelled", 1))).label("cancelled_bookings"),
            func.count(case(
                (
                    and_(
                        models.Booking.status == "active",
                        models.Booking.start_time <= now,
                        models.Booking.end_time > now,
                        models.Place.zone_id == models.Zone.id,
                    ),
                    1
                )
            )).label("current_occupancy"),
        )
        .outerjoin(models.Place, models.Place.zone_id == models.Zone.id)
        .outerjoin(models.Slot, models.Slot.place_id == models.Place.id)
        .outerjoin(models.Booking, models.Booking.slot_id == models.Slot.id)
        .where(models.Zone.id.in_(all_zone_ids))
        .group_by(models.Zone.id)
    )

    result_stats = await session.execute(stmt_stats)
    stats_map = {row.zone_id: row for row in result_stats}

    result_list = []
    for zone in zones:
        stats_row = stats_map.get(zone.id)
        result_list.append(schemas.ZoneOut(
            id=zone.id,
            name=zone.name,
            address=zone.address,
            is_active=zone.is_active,
            closure_reason=zone.closure_reason,
            closed_until=zone.closed_until,
            created_at=zone.created_at,
            updated_at=zone.updated_at,
            active_bookings=int(getattr(stats_row, "active_bookings", 0)),
            cancelled_bookings=int(getattr(stats_row, "cancelled_bookings", 0)),
            current_occupancy=int(getattr(stats_row, "current_occupancy", 0)),
        ))
    return result_list

async def get_places_by_zone(
    session: AsyncSession,
    zone_id: int,
) -> List[models.Place]:
    stmt = (
        select(models.Place)
        .where(
            and_(
                models.Place.zone_id == zone_id,
                models.Place.is_active.is_(True),
            )
        )
        .order_by(models.Place.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_slots_by_place_and_date(
    session: AsyncSession,
    place_id: int,
    target_date: date,
) -> List[models.Slot]:
    date_start = datetime.combine(target_date, datetime.min.time())
    date_end = datetime.combine(target_date, datetime.max.time())
    result = await session.execute(
        select(models.Slot)
        .where(
            and_(
                models.Slot.place_id == place_id,
                models.Slot.start_time >= date_start,
                models.Slot.start_time <= date_end,
            )
        )
        .order_by(models.Slot.start_time)
    )
    return list(result.scalars().all())

# ============================================================
#                      BOOKING ОПЕРАЦИИ
# ============================================================

async def check_user_booking_conflicts(
    session: AsyncSession,
    user_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_booking_id: Optional[int] = None,
) -> bool:
    stmt = select(models.Booking).where(
        and_(
            models.Booking.user_id == user_id,
            models.Booking.status == "active",
            models.Booking.start_time < end_time,
            models.Booking.end_time > start_time,
        )
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(models.Booking.id != exclude_booking_id)
    result = await session.execute(stmt)
    conflicting_bookings = result.scalars().all()
    return len(conflicting_bookings) > 0

async def create_booking(
    session: AsyncSession,
    user_id: int,
    booking_in: schemas.BookingCreate,
) -> Optional[models.Booking]:
    stmt = (
        select(models.Slot)
        .options(joinedload(models.Slot.place).joinedload(models.Place.zone))
        .where(models.Slot.id == booking_in.slot_id)
    )
    result = await session.execute(stmt)
    slot = result.scalar_one_or_none()
    if slot is None:
        return None
    if not slot.is_available:
        return None
    stmt = select(models.Booking).where(
        and_(
            models.Booking.user_id == user_id,
            models.Booking.slot_id == slot.id,
            models.Booking.status == "active",
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return None
    has_conflict = await check_user_booking_conflicts(
        session=session,
        user_id=user_id,
        start_time=slot.start_time,
        end_time=slot.end_time,
    )
    if has_conflict:
        return None
    zone = slot.place.zone if slot.place else None
    if zone:
        can_book = await check_zone_capacity(
            session=session,
            zone_id=zone.id,
            start_time=slot.start_time,
            end_time=slot.end_time,
        )
        if not can_book:
            return None
    zone = slot.place.zone if slot.place else None
    booking = models.Booking(
        user_id=user_id,
        slot_id=slot.id,
        status="active",
        zone_name=zone.name if zone else None,
        zone_address=zone.address if zone else None,
        start_time=slot.start_time,
        end_time=slot.end_time,
    )
    session.add(booking)
    slot.is_available = False
    await session.commit()
    await session.refresh(booking)
    
    # // уведомления: Отправляем email и push уведомление при создании бронирования
    await notify_booking_created(user_id, booking.zone_name, booking.start_time, booking.end_time)
    
    return booking

async def create_booking_by_time_range(
    session: AsyncSession,
    user_id: int,
    booking_in: schemas.BookingCreateTimeRange,
) -> Optional[models.Booking]:
    from datetime import datetime, timedelta, date as date_type
    
    try:
        target_date = date_type.fromisoformat(booking_in.date)
    except ValueError:
        return None
    
    start_time = datetime.combine(
        target_date,
        datetime.min.time().replace(
            hour=booking_in.start_hour,
            minute=booking_in.start_minute
        )
    )
    end_time = datetime.combine(
        target_date,
        datetime.min.time().replace(
            hour=booking_in.end_hour,
            minute=booking_in.end_minute
        )
    )
    # --- Исправление: сделали datetime "aware" (с таймзоной, теперь UTC) ---
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    # ----------------------------------------------------------------------
    duration = end_time - start_time
    if duration.total_seconds() <= 0:
        return None
    if duration.total_seconds() > settings.MAX_BOOKING_HOURS * 3600:
        return None
    zone = await session.get(models.Zone, booking_in.zone_id)
    if zone is None or not zone.is_active:
        return None
    has_conflict = await check_user_booking_conflicts(
        session=session,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
    )
    if has_conflict:
        return None
    can_book = await check_zone_capacity(
        session=session,
        zone_id=zone.id,
        start_time=start_time,
        end_time=end_time,
    )
    if not can_book:
        return None
    stmt = (
        select(models.Place)
        .where(
            and_(
                models.Place.zone_id == zone.id,
                models.Place.is_active.is_(True),
            )
        )
    )
    result = await session.execute(stmt)
    places = list(result.scalars().all())
    if not places:
        return None
    for place in places:
        stmt_exact = (
            select(models.Slot)
            .where(
                and_(
                    models.Slot.place_id == place.id,
                    models.Slot.start_time == start_time,
                    models.Slot.end_time == end_time,
                )
            )
        )
        result_exact = await session.execute(stmt_exact)
        exact_slot = result_exact.scalar_one_or_none()
        if exact_slot and exact_slot.is_available:
            exact_slot.is_available = False
            booking = models.Booking(
                user_id=user_id,
                slot_id=exact_slot.id,
                status="active",
                zone_name=zone.name,
                zone_address=zone.address,
                start_time=start_time,
                end_time=end_time,
            )
            session.add(booking)
            await session.commit()
            await session.refresh(booking)
            
            # // уведомления: Отправляем email и push уведомление при создании бронирования
            await notify_booking_created(user_id, booking.zone_name, booking.start_time, booking.end_time)
            
            return booking
        if exact_slot and not exact_slot.is_available:
            continue
        if not exact_slot:
            stmt = (
                select(models.Slot)
                .where(
                    and_(
                        models.Slot.place_id == place.id,
                        models.Slot.start_time < end_time,
                        models.Slot.end_time > start_time,
                    )
                )
            )
            result = await session.execute(stmt)
            overlapping_slots = list(result.scalars().all())
            has_conflict = False
            for slot in overlapping_slots:
                if not slot.is_available:
                    has_conflict = True
                    break
            if not has_conflict:
                slot = models.Slot(
                    place_id=place.id,
                    start_time=start_time,
                    end_time=end_time,
                    is_available=False,
                )
                session.add(slot)
                await session.flush()
                booking = models.Booking(
                    user_id=user_id,
                    slot_id=slot.id,
                    status="active",
                    zone_name=zone.name,
                    zone_address=zone.address,
                    start_time=start_time,
                    end_time=end_time,
                )
                session.add(booking)
                await session.commit()
                await session.refresh(booking)
                
                # // уведомления: Отправляем email и push уведомление при создании бронирования
                await notify_booking_created(user_id, booking.zone_name, booking.start_time, booking.end_time)
                
                return booking
    return None

async def get_booking_by_id(
    session: AsyncSession,
    booking_id: int,
) -> Optional[models.Booking]:
    stmt = (
        select(models.Booking)
        .options(joinedload(models.Booking.slot))
        .where(models.Booking.id == booking_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def cancel_booking(
    session: AsyncSession,
    user_id: int,
    booking_id: int,
    *,
    is_admin: bool = False,
) -> Optional[models.Booking]:
    booking = await get_booking_by_id(session, booking_id)
    if booking is None:
        return None
    if not is_admin and booking.user_id != user_id:
        return None
    if booking.status != "active":
        return booking
    booking.status = "cancelled"
    if booking.slot:
        booking.slot.is_available = True
    await session.commit()
    await session.refresh(booking)
    
    # // уведомления: Отправляем email и push уведомление при отмене бронирования
    await notify_booking_cancelled(booking.user_id, booking.zone_name, booking.start_time, booking.end_time)
    
    return booking

async def get_booking_history(
    session: AsyncSession,
    user_id: int,
    filters: Optional[schemas.BookingHistoryFilters] = None,
) -> List[models.Booking]:
    filters = filters or schemas.BookingHistoryFilters()
    stmt = (
        select(models.Booking)
        .join(models.Slot, models.Slot.id == models.Booking.slot_id)
        .join(models.Place, models.Place.id == models.Slot.place_id)
        .join(models.Zone, models.Zone.id == models.Place.zone_id)
        .where(models.Booking.user_id == user_id)
        .options(joinedload(models.Booking.slot))
        .order_by(models.Booking.created_at.desc())
    )
    conds = []
    if filters.status:
        conds.append(models.Booking.status == filters.status)
    if filters.zone_id:
        conds.append(models.Zone.id == filters.zone_id)
    if filters.date_from:
        conds.append(models.Slot.start_time >= filters.date_from)
    if filters.date_to:
        conds.append(models.Slot.start_time <= filters.date_to)
    if conds:
        stmt = stmt.where(and_(*conds))
    result = await session.execute(stmt)
    return list(result.scalars().all())

class BookingExtensionError(Exception):
    pass

async def extend_booking(
    session: AsyncSession,
    user_id: int,
    booking_id: int,
    extend_hours: int = 1,
    extend_minutes: int = 0,
) -> models.Booking:
    booking = await get_booking_by_id(session, booking_id)
    if booking is None:
        raise BookingExtensionError("Бронирование не найдено")
    if booking.user_id != user_id:
        raise BookingExtensionError("Нет прав на продление этого бронирования")
    if booking.status != "active":
        raise BookingExtensionError("Можно продлить только активное бронирование")
    if booking.start_time is None or booking.end_time is None:
        raise BookingExtensionError("Некорректные данные бронирования")
    slot = booking.slot
    if slot is None:
        raise BookingExtensionError("Слот бронирования не найден")
    new_end_time = booking.end_time + timedelta(hours=extend_hours, minutes=extend_minutes)
    total_duration = new_end_time - booking.start_time
    if total_duration.total_seconds() > settings.MAX_BOOKING_HOURS * 3600:
        raise BookingExtensionError(
            f"Превышен максимальный лимит бронирования ({settings.MAX_BOOKING_HOURS} часов)"
        )
    has_conflict = await check_user_booking_conflicts(
        session=session,
        user_id=user_id,
        start_time=booking.end_time,
        end_time=new_end_time,
        exclude_booking_id=booking_id,
    )
    if has_conflict:
        raise BookingExtensionError(
            "У вас уже есть другое бронирование на это время"
        )
    zone = None
    if slot.place:
        stmt = (
            select(models.Place)
            .options(joinedload(models.Place.zone))
            .where(models.Place.id == slot.place_id)
        )
        result = await session.execute(stmt)
        place = result.scalar_one_or_none()
        if place and place.zone:
            zone = place.zone
    if zone is None:
        raise BookingExtensionError("Зона не найдена")
    can_book = await check_zone_capacity(
        session=session,
        zone_id=zone.id,
        start_time=booking.end_time,
        end_time=new_end_time,
    )
    if not can_book:
        raise BookingExtensionError(
            "Зона переполнена на выбранное время. Попробуйте продлить на меньшее время"
        )
    stmt_exact = (
        select(models.Slot)
        .where(
            and_(
                models.Slot.place_id == slot.place_id,
                models.Slot.start_time == booking.end_time,
                models.Slot.end_time == new_end_time,
            )
        )
    )
    result_exact = await session.execute(stmt_exact)
    extended_slot = result_exact.scalar_one_or_none()
    if extended_slot and extended_slot.is_available:
        extended_slot.is_available = False
    elif extended_slot and not extended_slot.is_available:
        raise BookingExtensionError(
            "Выбранное время уже занято. Попробуйте продлить на меньшее время"
        )
    else:
        stmt_overlap = (
            select(models.Slot)
            .where(
                and_(
                    models.Slot.place_id == slot.place_id,
                    models.Slot.start_time < new_end_time,
                    models.Slot.end_time > booking.end_time,
                )
            )
        )
        result_overlap = await session.execute(stmt_overlap)
        overlapping_slots = list(result_overlap.scalars().all())
        for overlap_slot in overlapping_slots:
            if not overlap_slot.is_available:
                raise BookingExtensionError(
                    "Выбранное время частично занято. Попробуйте продлить на меньшее время"
                )
        extended_slot = models.Slot(
            place_id=slot.place_id,
            start_time=booking.end_time,
            end_time=new_end_time,
            is_available=False,
        )
        session.add(extended_slot)
        await session.flush()
    new_booking = models.Booking(
        user_id=user_id,
        slot_id=extended_slot.id,
        status="active",
        zone_name=zone.name if zone else None,
        zone_address=zone.address if zone else None,
        start_time=booking.end_time,
        end_time=new_end_time,
    )
    session.add(new_booking)
    await session.commit()
    await session.refresh(new_booking)
    
    # // уведомления: Отправляем email и push уведомление при продлении бронирования
    await notify_booking_extended(user_id, new_booking.zone_name, new_booking.end_time)
    
    return new_booking

# ============================================================
#                      АДМИНСКИЕ ОПЕРАЦИИ
# ============================================================

async def create_zone(
    session: AsyncSession,
    data: schemas.ZoneCreate,
) -> models.Zone:
    zone = models.Zone(
        name=data.name,
        address=data.address,
        is_active=data.is_active,
    )
    session.add(zone)
    await session.flush()
    for i in range(1, data.places_count + 1):
        place = models.Place(
            zone_id=zone.id,
            name=f"Место {i}",
            is_active=True,
        )
        session.add(place)
    await session.commit()
    await session.refresh(zone)
    return zone

async def update_zone(
    session: AsyncSession,
    zone_id: int,
    data: schemas.ZoneUpdate,
) -> Optional[models.Zone]:
    zone = await session.get(models.Zone, zone_id)
    if zone is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(zone, field, value)
    await session.commit()
    await session.refresh(zone)
    return zone

async def delete_zone(
    session: AsyncSession,
    zone_id: int,
) -> bool:
    zone = await session.get(models.Zone, zone_id)
    if zone is None:
        return False
    await session.delete(zone)
    await session.commit()
    return True

async def close_zone(
    session: AsyncSession,
    zone_id: int,
    data: schemas.ZoneCloseRequest,
) -> List[models.Booking]:
    zone = await session.get(models.Zone, zone_id)
    if zone is None:
        return []
    zone.is_active = False
    zone.closure_reason = data.reason
    zone.closed_until = data.to_time
    stmt = (
        select(models.Booking)
        .join(models.Slot, models.Slot.id == models.Booking.slot_id)
        .join(models.Place, models.Place.id == models.Slot.place_id)
        .join(models.Zone, models.Zone.id == models.Place.zone_id)
        .where(
            and_(
                models.Zone.id == zone_id,
                models.Booking.status == "active",
                models.Slot.start_time < data.to_time,
                models.Slot.end_time  > data.from_time,
            )
        )
        .options(joinedload(models.Booking.slot))
    )
    result = await session.execute(stmt)
    affected_bookings: List[models.Booking] = list(result.scalars().all())
    for booking in affected_bookings:
        booking.status = "cancelled"
        booking.cancellation_reason = f"Зона закрыта: {data.reason}"
        if booking.slot:
            booking.slot.is_available = True
    await session.commit()
    await session.refresh(zone)
    for booking in affected_bookings:
        await session.refresh(booking)
    
    # // уведомления: Отправляем email и push уведомление всем затронутым пользователям о закрытии зоны
    for booking in affected_bookings:
        await notify_zone_closed(
            booking.user_id,
            zone.name,
            data.reason,
            booking.start_time,
            booking.end_time
        )
    
    return affected_bookings

async def get_global_statistics(
    session: AsyncSession,
) -> schemas.GlobalStatistics:
    stmt = select(
        func.count(models.Booking.id).filter(models.Booking.status == "active").label("active_count"),
        func.count(models.Booking.id).filter(models.Booking.status == "cancelled").label("cancelled_count"),
    )
    result = await session.execute(stmt)
    row = result.one()
    total_active = row.active_count or 0
    total_cancelled = row.cancelled_count or 0
    now = msk_to_utc(now_msk())
    stmt = select(func.count(func.distinct(models.Booking.user_id))).where(
        and_(
            models.Booking.status == "active",
            models.Booking.start_time <= now,
            models.Booking.end_time > now,
        )
    )
    result = await session.execute(stmt)
    users_now = result.scalar() or 0
    return schemas.GlobalStatistics(
        total_active_bookings=total_active,
        total_cancelled_bookings=total_cancelled,
        users_in_coworking_now=users_now,
    )

async def check_zone_capacity(
    session: AsyncSession,
    zone_id: int,
    start_time: datetime,
    end_time: datetime,
) -> bool:
    stmt = select(func.count(models.Place.id)).where(
        and_(
            models.Place.zone_id == zone_id,
            models.Place.is_active.is_(True),
        )
    )
    result = await session.execute(stmt)
    max_capacity = result.scalar() or 0
    if max_capacity == 0:
        return False
    stmt = (
        select(models.Booking)
        .join(models.Slot, models.Slot.id == models.Booking.slot_id)
        .join(models.Place, models.Place.id == models.Slot.place_id)
        .where(
            and_(
                models.Place.zone_id == zone_id,
                models.Booking.status == "active",
                models.Booking.start_time < end_time,
                models.Booking.end_time > start_time,
            )
        )
    )
    result = await session.execute(stmt)
    overlapping_bookings = list(result.scalars().all())
    time_points = []
    time_points.append(start_time)
    time_points.append(end_time)
    for booking in overlapping_bookings:
        if booking.start_time and booking.end_time:
            time_points.append(booking.start_time)
            time_points.append(booking.end_time)
    # --- Исправление ключевой ошибки: привести все точки к aware-UTC ---
    time_points = [
        dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        for dt in time_points
    ]
    time_points = sorted(set(time_points))
    # --------------------------------------------------------------
    for check_time in time_points:
        if check_time < start_time or check_time >= end_time:
            continue
        active_count = 0
        for booking in overlapping_bookings:
            if (booking.start_time and booking.end_time and
                booking.start_time <= check_time < booking.end_time):
                active_count += 1
        if start_time <= check_time < end_time:
            active_count += 1
        if active_count > max_capacity:
            return False
    return True