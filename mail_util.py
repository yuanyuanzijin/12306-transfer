import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import parseaddr, formataddr
from config import LOG_DIR


if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)
logging.basicConfig(filename=LOG_DIR + 'mail.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class Mail(object):
    def __init__(self, mail_host, mail_port, mail_user, mail_pass, sender_name, email_addr):
        self.mail_host = mail_host
        self.mail_port = mail_port
        self.mail_user = mail_user
        self.mail_pass = mail_pass
        self.sender_name = sender_name
        self.mailto = email_addr
        self.mail_log = logging.getLogger(__name__)


    def __format_addr(self, s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, 'utf-8').encode(), addr))


    def send_mail(self, subject="发现可行换乘方案", content=""):
        if type(self.mailto) == str:
            receivers = [self.mailto]
        else:
            receivers = self.mailto

        sender = self.__format_addr("%s <%s>" % (self.sender_name, self.mail_user))
        self.message = MIMEMultipart()
        self.message['From'] = sender
        self.message['To'] = ";".join(receivers)
        self.message['Subject'] = Header(subject, 'utf-8')
        self.message.attach(MIMEText(content, 'html', 'utf-8'))

        try:
            smtpObj = smtplib.SMTP_SSL(host=self.mail_host)
            smtpObj.connect(self.mail_host, self.mail_port)
            smtpObj.login(self.mail_user, self.mail_pass)
            smtpObj.sendmail(sender, receivers, self.message.as_string())
            for receive in receivers:
                self.mail_log.info(f"邮件发送成功！主题：{subject}，收件人：{receive}")
            return True
        except smtplib.SMTPException as e:
            self.mail_log.error(f"邮件发送失败！主题：{subject}，失败原因：{e}")
            return False
