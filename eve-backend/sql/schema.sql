-- EVE Healthcare — Diagnostic Booking System
-- Target: Microsoft SQL Server 2019+
--
-- Design notes (also explained in README):
--   * Booking.amount is captured at booking time (snapshot of Test.price)
--     so later price changes on a test never retroactively change what a
--     user already booked / paid for.
--   * PaymentEvent has a UNIQUE constraint on event_id -- this is what makes
--     the webhook idempotent. A duplicate delivery is rejected by the DB
--     constraint itself, not just application-level logic, so it holds even
--     under concurrent duplicate requests.
--   * Booking.status transitions are enforced in application code
--     (see app/routes/payments.py) rather than DB triggers, to keep the
--     schema portable and the transition logic easy to unit test.

IF DB_ID('eve_healthcare') IS NULL
BEGIN
    CREATE DATABASE eve_healthcare;
END
GO

USE eve_healthcare;
GO

IF OBJECT_ID('dbo.PaymentEvents', 'U') IS NOT NULL DROP TABLE dbo.PaymentEvents;
IF OBJECT_ID('dbo.Payments', 'U') IS NOT NULL DROP TABLE dbo.Payments;
IF OBJECT_ID('dbo.Bookings', 'U') IS NOT NULL DROP TABLE dbo.Bookings;
IF OBJECT_ID('dbo.Tests', 'U') IS NOT NULL DROP TABLE dbo.Tests;
IF OBJECT_ID('dbo.Centres', 'U') IS NOT NULL DROP TABLE dbo.Centres;
IF OBJECT_ID('dbo.Users', 'U') IS NOT NULL DROP TABLE dbo.Users;
GO

CREATE TABLE dbo.Users (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    name            NVARCHAR(150)   NOT NULL,
    email           NVARCHAR(255)   NOT NULL UNIQUE,
    password_hash   NVARCHAR(255)   NOT NULL,
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.Centres (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    name            NVARCHAR(200)   NOT NULL,
    location        NVARCHAR(255)   NOT NULL,
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.Tests (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    centre_id       INT             NOT NULL FOREIGN KEY REFERENCES dbo.Centres(id),
    name            NVARCHAR(200)   NOT NULL,
    price           DECIMAL(10,2)   NOT NULL CHECK (price >= 0),
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.Bookings (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    user_id             INT             NOT NULL FOREIGN KEY REFERENCES dbo.Users(id),
    test_id             INT             NOT NULL FOREIGN KEY REFERENCES dbo.Tests(id),
    centre_id           INT             NOT NULL FOREIGN KEY REFERENCES dbo.Centres(id),
    appointment_time    DATETIME2       NOT NULL,
    amount              DECIMAL(10,2)   NOT NULL CHECK (amount >= 0),
    status              NVARCHAR(20)    NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED')),
    created_at          DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.Payments (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    booking_id          INT             NOT NULL FOREIGN KEY REFERENCES dbo.Bookings(id),
    amount              DECIMAL(10,2)   NOT NULL,
    status              NVARCHAR(20)    NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    provider_reference  NVARCHAR(100)   NULL,
    created_at          DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- Backs webhook idempotency: event_id is UNIQUE, so a duplicate delivery
-- of the same provider event fails the INSERT (handled gracefully in code)
-- instead of ever being processed twice.
CREATE TABLE dbo.PaymentEvents (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    event_id            NVARCHAR(100)   NOT NULL UNIQUE,
    booking_id          INT             NOT NULL FOREIGN KEY REFERENCES dbo.Bookings(id),
    status              NVARCHAR(20)    NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    raw_payload         NVARCHAR(MAX)   NULL,
    created_at          DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE INDEX IX_Tests_centre_id ON dbo.Tests(centre_id);
CREATE INDEX IX_Bookings_user_id ON dbo.Bookings(user_id);
CREATE INDEX IX_Bookings_status ON dbo.Bookings(status);
GO
