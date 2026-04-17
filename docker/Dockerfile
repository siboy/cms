FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    default-libmysqlclient-dev pkg-config \
    curl git tmux cron \
    libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/databoks/cms

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/cache data/uploads

EXPOSE 8879

COPY docker/startup.sh /home/startup/startup.sh
RUN chmod +x /home/startup/startup.sh

ENTRYPOINT ["/home/startup/startup.sh"]
