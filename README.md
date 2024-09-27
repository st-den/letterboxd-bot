# letterboxd-bot
## Setup
```
$ ssh user@vps
$ sudo apt install python3-pip python3-venv git screen
$ git clone https://github.com/st-den/letterboxd-bot.git
$ cd letterboxd-bot
$ nano prod.env
$ nano users.txt
$ python -m venv bot
$ source bot/bin/activate
$ pip install -r requirements.txt
$ screen -dmS bot bash -c 'source venv/bin/activate && python bot.py'
```
