# Domoticz-Xiaomi-Fan-ZA4



pre requisite:

sudo apt-get install python3 python3-dev python3-pip

sudo apt-get install libffi-dev libssl-dev

sudo pip3 install -U setuptools

sudo pip3 install -U virtualenv

git clone https://github.com/Condorello/Domoticz-Xiaomi-Fan-ZA4.git xiaomi-fanza4
cd xiaomi-fanza4
virtualenv -p python3 .env
source .env/bin/activate

pip3 install -r pip_req.txt 
