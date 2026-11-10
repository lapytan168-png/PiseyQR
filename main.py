import os
import secrets
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATABASE_PATH = Path(__file__).with_name("hotel.db")
ACTIVE_BOOKING_STATUSES = ("pending", "confirmed")
app = FastAPI(title="Sokha Haven Hotel API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)


class BookingRequest(BaseModel):
    room_id: int = Field(gt=0)
    guest_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(min_length=6, max_length=30)
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=20)


class RoomRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=10, max_length=500)
    image: str = Field(min_length=1, max_length=500)
    price: int = Field(ge=1, le=1000000)
    capacity: int = Field(ge=1, le=20)
    amenities: list[str] = Field(min_items=1, max_items=12)


class BookingStatusRequest(BaseModel):
    status: str


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_db() -> None:
    with connect_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL,
                price INTEGER NOT NULL CHECK (price > 0),
                capacity INTEGER NOT NULL CHECK (capacity > 0),
                amenities TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                guest_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                guests INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        room_count = connection.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        if room_count == 0:
            rooms = [
                (
                    "Garden Retreat",
                    "Deluxe Room",
                    "បន្ទប់ធំទូលាយជាមួយទេសភាពសួនច្បារ និងពន្លឺធម្មជាតិ។",
                    "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=1100&q=85",
                    89,
                    2,
                    "King bed,Private balcony,Garden view",
                ),
                (
                    "Mekong Suite",
                    "Premium Suite",
                    "សម្រាកយ៉ាងស្ងប់ស្ងាត់ក្នុងឈុតបន្ទប់ស្រស់ស្អាត ជាមួយកន្លែងអង្គុយផ្ទាល់ខ្លួន។",
                    "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=1100&q=85",
                    149,
                    3,
                    "King bed,Lounge area,River view",
                ),
                (
                    "Heritage Villa",
                    "Private Villa",
                    "វីឡាឯកជនលំដាប់ខ្ពស់ មានអាងហែលទឹក និងសួនត្រូពិចផ្ទាល់ខ្លួន។",
                    "https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=1100&q=85",
                    229,
                    4,
                    "Private pool,Two bedrooms,Outdoor terrace",
                ),
            ]
            connection.executemany(
                """
                INSERT INTO rooms (name, category, description, image, price, capacity, amenities)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rooms,
            )


def admin_required(authorization: Optional[str] = Header(default=None)) -> None:
    admin_token = os.getenv("ADMIN_TOKEN")
    if not admin_token:
        raise HTTPException(status_code=503, detail="Admin access is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required.")
    supplied_token = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(supplied_token, admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def room_dict(row: sqlite3.Row) -> dict:
    room = dict(row)
    room["amenities"] = room["amenities"].split(",")
    room["active"] = bool(room["active"])
    return room


@app.on_event("startup")
def startup() -> None:
    initialize_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/rooms")
def list_rooms(
    check_in: Optional[date] = Query(default=None),
    check_out: Optional[date] = Query(default=None),
) -> list[dict]:
    if (check_in is None) != (check_out is None):
        raise HTTPException(status_code=422, detail="Both check-in and check-out dates are required.")
    if check_in and check_out and check_out <= check_in:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in.")

    with connect_db() as connection:
        if check_in and check_out:
            rows = connection.execute(
                """
                SELECT r.* FROM rooms r
                WHERE r.active = 1 AND NOT EXISTS (
                    SELECT 1 FROM bookings b
                    WHERE b.room_id = r.id
                      AND b.status IN (?, ?)
                      AND b.check_in < ?
                      AND b.check_out > ?
                )
                ORDER BY r.id
                """,
                (*ACTIVE_BOOKING_STATUSES, check_out.isoformat(), check_in.isoformat()),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM rooms WHERE active = 1 ORDER BY id"
            ).fetchall()
    return [room_dict(row) for row in rows]


@app.post("/api/bookings", status_code=201)
def create_booking(booking: BookingRequest) -> dict:
    if booking.check_out <= booking.check_in:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in.")
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        room = connection.execute(
            "SELECT id, capacity FROM rooms WHERE id = ? AND active = 1",
            (booking.room_id,),
        ).fetchone()
        if room is None:
            raise HTTPException(status_code=404, detail="This room is no longer available.")
        if booking.guests > room["capacity"]:
            raise HTTPException(status_code=422, detail="Guest count exceeds room capacity.")
        conflict = connection.execute(
            """
            SELECT 1 FROM bookings
            WHERE room_id = ? AND status IN (?, ?)
              AND check_in < ? AND check_out > ?
            LIMIT 1
            """,
            (
                booking.room_id,
                *ACTIVE_BOOKING_STATUSES,
                booking.check_out.isoformat(),
                booking.check_in.isoformat(),
            ),
        ).fetchone()
        if conflict:
            raise HTTPException(status_code=409, detail="This room was just booked for those dates.")
        cursor = connection.execute(
            """
            INSERT INTO bookings
                (room_id, guest_name, email, phone, check_in, check_out, guests)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                booking.room_id,
                booking.guest_name.strip(),
                booking.email.strip(),
                booking.phone.strip(),
                booking.check_in.isoformat(),
                booking.check_out.isoformat(),
                booking.guests,
            ),
        )
        result = connection.execute(
            """
            SELECT b.*, r.name AS room_name, r.price AS nightly_price
            FROM bookings b JOIN rooms r ON r.id = b.room_id
            WHERE b.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(result)


@app.get("/api/admin/bookings", dependencies=[Depends(admin_required)])
def list_bookings() -> list[dict]:
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT b.*, r.name AS room_name, r.price AS nightly_price
            FROM bookings b JOIN rooms r ON r.id = b.room_id
            ORDER BY b.created_at DESC, b.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/admin/rooms", dependencies=[Depends(admin_required)])
def list_admin_rooms() -> list[dict]:
    with connect_db() as connection:
        rows = connection.execute("SELECT * FROM rooms ORDER BY id").fetchall()
    return [room_dict(row) for row in rows]


@app.post("/api/admin/rooms", status_code=201, dependencies=[Depends(admin_required)])
def create_room(room: RoomRequest) -> dict:
    with connect_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO rooms (name, category, description, image, price, capacity, amenities)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room.name.strip(),
                room.category.strip(),
                room.description.strip(),
                room.image.strip(),
                room.price,
                room.capacity,
                ",".join(item.strip() for item in room.amenities if item.strip()),
            ),
        )
        result = connection.execute(
            "SELECT * FROM rooms WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return room_dict(result)


@app.patch("/api/admin/rooms/{room_id}", dependencies=[Depends(admin_required)])
def update_room(room_id: int, room: RoomRequest) -> dict:
    with connect_db() as connection:
        cursor = connection.execute(
            """
            UPDATE rooms
            SET name = ?, category = ?, description = ?, image = ?,
                price = ?, capacity = ?, amenities = ?
            WHERE id = ?
            """,
            (
                room.name.strip(),
                room.category.strip(),
                room.description.strip(),
                room.image.strip(),
                room.price,
                room.capacity,
                ",".join(item.strip() for item in room.amenities if item.strip()),
                room_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Room not found.")
        result = connection.execute(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
    return room_dict(result)


@app.patch("/api/admin/rooms/{room_id}/availability", dependencies=[Depends(admin_required)])
def set_room_availability(room_id: int, active: bool = Query(...)) -> dict:
    with connect_db() as connection:
        cursor = connection.execute(
            "UPDATE rooms SET active = ? WHERE id = ?", (int(active), room_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Room not found.")
        result = connection.execute(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
    return room_dict(result)


@app.patch("/api/admin/bookings/{booking_id}", dependencies=[Depends(admin_required)])
def update_booking_status(booking_id: int, request: BookingStatusRequest) -> dict:
    if request.status not in {"pending", "confirmed", "cancelled", "completed"}:
        raise HTTPException(status_code=422, detail="Invalid booking status.")
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        booking = connection.execute(
            "SELECT * FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")
        if request.status in ACTIVE_BOOKING_STATUSES:
            conflict = connection.execute(
                """
                SELECT 1 FROM bookings
                WHERE id != ? AND room_id = ? AND status IN (?, ?)
                  AND check_in < ? AND check_out > ?
                LIMIT 1
                """,
                (
                    booking_id,
                    booking["room_id"],
                    *ACTIVE_BOOKING_STATUSES,
                    booking["check_out"],
                    booking["check_in"],
                ),
            ).fetchone()
            if conflict:
                raise HTTPException(status_code=409, detail="Another active booking overlaps these dates.")
        connection.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (request.status, booking_id),
        )
        result = connection.execute(
            """
            SELECT b.*, r.name AS room_name, r.price AS nightly_price
            FROM bookings b JOIN rooms r ON r.id = b.room_id
            WHERE b.id = ?
            """,
            (booking_id,),
        ).fetchone()
    return dict(result)
