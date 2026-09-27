FROM python:3.12-slim

WORKDIR /app

# pymssql wheels bundle FreeTDS, so no extra system ODBC driver is needed --
# this is one of the reasons pymssql was chosen over pyodbc for this project.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "run:app"]
