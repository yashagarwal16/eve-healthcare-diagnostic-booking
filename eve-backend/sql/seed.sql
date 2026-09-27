-- Optional sample data for manual/local testing
USE eve_healthcare;
GO

INSERT INTO dbo.Centres (name, location) VALUES
    (N'CityCare Diagnostics', N'Jaipur, Rajasthan'),
    (N'MediPath Labs', N'Delhi, NCR');
GO

INSERT INTO dbo.Tests (centre_id, name, price) VALUES
    (1, N'Complete Blood Count (CBC)', 350.00),
    (1, N'Lipid Profile', 600.00),
    (1, N'Thyroid Panel (T3 T4 TSH)', 750.00),
    (2, N'HbA1c', 450.00),
    (2, N'Vitamin D Test', 900.00);
GO
