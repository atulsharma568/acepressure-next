"""QR to the PUBLIC TIP PAGE, not a static UPI payment."""
import os,sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
import qrcode
load_dotenv(ROOT/'.env');url=os.getenv('PUBLIC_BASE_URL','')
if urlparse(url).scheme!='https':sys.exit('Configure your stable HTTPS PUBLIC_BASE_URL first.')
folder=ROOT/'data';folder.mkdir(exist_ok=True)
p=folder/'AcePressure_Tip_Page_QR.png';qrcode.make(url+'/tip/acepressure').save(p);print('Created',p)
