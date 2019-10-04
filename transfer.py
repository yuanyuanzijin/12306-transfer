import os
import re
import time
import json
import logging
import sqlite3
import itertools
from urllib import parse
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import parseaddr, formataddr

from config import LOG_DIR


if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)
logging.basicConfig(filename=LOG_DIR + 'transfer.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class Transfer(object):
    """
    12306换乘查询类
    """
    __tf_version__ = '2.0'
    __update_time__ = '2019/10/04'


    def __init__(self, date, transfer_cities, max_transfer_times, expect_total_time, retry_times, expire_time,
                 min_expire_time, auto_expire):
        self.date = date                                # 出发日期
        self.transfer_cities = transfer_cities          # 换乘城市
        self.max_transfer_times = max_transfer_times    # 最大换乘次数
        self.expect_total_time = expect_total_time      # 期望最长总时长
        self.retry_times = retry_times                  # 网络重试次数
        self.expire_time = expire_time                  # 初始缓存时间
        self.min_expire_time = min_expire_time          # 最短缓存时间
        self.auto_expire = auto_expire                  # 自适应缓存时间

        self.tf_log = logging.getLogger(__name__)
        self.db = Database()
        self.s = requests.Session()

        self.interval = 0
        self.count_online = 0
        self.count_cache = 0
        self.current_result = []
        self.mail_mq = []
        self.last_round_time = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/63.0.3239.26 Safari/537.36 Core/1.63.5702.400 QQBrowser/10.2.1893.400"
        }
        self.to_code, self.to_name = self.__get_station_code_and_name()
        self.tasks = self.__generate_task_list()


    def __get_station_code_and_name(self):
        """
        获取车站代码转换字典
        :return:
        """
        url = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js?station_version=1.9112"
        response = self.s.get(url, headers=self.headers)
        stations = re.findall(r'([\u4e00-\u9fa5]+)\|([A-Z]+)', response.text)
        to_code = dict(stations)
        to_name = dict(zip(to_code.values(), to_code.keys()))
        return to_code, to_name


    def __generate_task_list(self):
        """
        生成任务列表
        :return:
        """
        # 生成换乘线路任务列表
        tasks = []
        range_list = list(range(1, len(self.transfer_cities) - 1))
        for transfer_times in range(self.max_transfer_times + 1):
            for indices_method in itertools.combinations(range_list, transfer_times):
                choose_cities_indices = sorted(indices_method)
                choose_cities_indices.insert(0, 0)
                choose_cities_indices.append(-1)
                tasks.append(choose_cities_indices)
        self.tf_log.info(f"任务列表获取完成，共有{len(tasks)}种方案，准备开始任务...")
        return tasks


    def get_tickets(self, from_city, arrive_city):
        """
        获取指定两个城市之间的余票信息
        :return:
        """
        sql = "select * from transfer where from_date=? and from_city=? and arrive_city=? order by update_time desc"
        params = [self.date, from_city, arrive_city]
        db_result = self.db.getall(sql, params)

        self.cache = False
        if db_result:
            self.db_mode = "update"
            cache_time = db_result[0]['update_time']
            cache_time_stamp = time.mktime(time.strptime(cache_time, '%Y-%m-%d %H:%M:%S'))
            if time.time() - cache_time_stamp < self.expire_time:
                self.cache = True
        else:
            self.db_mode = "insert"

        if self.cache:
            stage_result = self.get_tickets_from_cache(db_result)
        else:
            stage_result = self.get_tickets_from_12306(from_city, arrive_city)
        return stage_result


    def get_tickets_from_cache(self, db_result):
        """
        将数据库取出来的数据整理为可以使用的数据
        :param db_result:
        :return:
        """
        self.count_cache += 1
        stage_result = []
        for line in db_result:
            has_ticket = line['has_ticket']
            res = [line['code'], line['from_code'], line['arrive_code'], line['from_time'], line['arrive_time']]
            if has_ticket == 1:
                stage_result.append(res)
        return stage_result


    def get_tickets_from_12306(self, from_city, arrive_city):
        """
        从12306中在线获取余票信息
        :param from_station_name:
        :param to_station_name:
        :return:
        """
        self.count_online += 1
        from_station_code = self.to_code[from_city]
        to_station_code = self.to_code[arrive_city]
        cookies = {
            "_jc_save_fromStation": parse.quote(f"{from_city},{from_station_code}"),
            "_jc_save_toStation": parse.quote(f"{arrive_city},{to_station_code}"),
            "_jc_save_fromDate": self.date,
            "_jc_save_toDate": "2019-10-01",
            "_jc_save_wfdc_flag": "dc"
        }
        url_ticket = f"https://kyfw.12306.cn/otn/leftTicket/queryA?leftTicketDTO.train_date={self.date}" \
                     f"&leftTicketDTO.from_station={from_station_code}" \
                     f"&leftTicketDTO.to_station={to_station_code}&purpose_codes=ADULT"
        retry_times = self.retry_times
        while retry_times:
            try:
                req = self.s.get(url_ticket, headers=self.headers, cookies=cookies)
                infos = json.loads(req.text)["data"]["result"]
                break
            except Exception as e:
                time.sleep(1)
                retry_times -= 1
        else:
            self.tf_log.error("方案获取失败")
            return False

        stage_result = []
        for info in infos:
            item = info.split('|')
            data = {}
            data["station_train_code"] = item[3]  # 获取车次信息，在3号位置
            data["from_station_name"] = item[6]  # 始发站信息在6号位置
            data["to_station_name"] = item[7]  # 终点站信息在7号位置
            data["start_time"] = item[8]  # 出发时间在8号位置
            data["arrive_time"] = item[9]  # 抵达时间在9号位置
            data["zy_num"] = item[31]  # 一等座信息在31号位置
            data["ze_num"] = item[30]  # 二等座信息在30号位置
            data["gr_num"] = item[21]  # 高级软卧信息在21号位置
            data["rw_num"] = item[23]  # 软卧信息在23号位置
            data["dw_num"] = item[27]  # 动卧信息在27号位置
            data["yw_num"] = item[28]  # 硬卧信息在28号位置
            data["rz_num"] = item[24]  # 软座信息在24号位置
            data["yz_num"] = item[29]  # 硬座信息在29号位置
            data["wz_num"] = item[26]  # 无座信息在26号位置
            if "有" in [item[31], item[30], item[29], item[26], item[24], item[28], item[23], item[27]]:
                has_ticket = 1
            else:
                has_ticket = 0

            res_code = data['station_train_code']
            res_from_code = data['from_station_name']
            res_from_time = data['start_time']
            res_arrive_code = data['to_station_name']
            res_arrive_time = data['arrive_time']

            if self.db_mode == "insert":
                sql = "insert into transfer (code, from_date, from_city, arrive_city, from_code, from_time, " \
                      "arrive_code, arrive_time, has_ticket) values (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                params = [res_code, self.date, from_city, arrive_city, res_from_code, res_from_time,
                          res_arrive_code, res_arrive_time, has_ticket]
            elif self.db_mode == "update":
                sql = "update transfer set has_ticket=?, update_time=(datetime('now','localtime')) " \
                      "where code=? and from_date=? and from_code=? and arrive_code=?"
                params = [has_ticket, res_code, self.date, res_from_code, res_arrive_code]
            else:
                raise ValueError("db_mode错误！")
            self.db.save(sql, params)

            if has_ticket == 1:
                res = [res_code, res_from_code, res_arrive_code, res_from_time, res_arrive_time]
                stage_result.append(res)
        return stage_result


    def filter_global_result(self, stage=0, last_end_time=None, history=None):
        """
        对当前搜索结果进行筛选，计算符合时间的方案
        :param stage:
        :param last_end_time:
        :param history:
        :return:
        """
        if not last_end_time:
            last_end_time = "00:00"
        if not history:
            history = []

        if stage == len(self.global_result):
            h1, m1 = self.global_result[history[0][0]][history[0][1]][3].split(":")
            h2, m2 = self.global_result[history[-1][0]][history[-1][1]][4].split(":")
            h = int(h2) - int(h1)
            m = int(m2) - int(m1)
            if h >= self.expect_total_time:
                return
            if m < 0:
                m += 60
                h -= 1
            info_list = [(self.date, h, m)]
            for hist in history:
                info = self.global_result[hist[0]][hist[1]]
                info_list.append(f"{self.to_name[info[1]]}({info[3]}) --{info[0]}--> ({info[4]}){self.to_name[info[2]]}")

            # 在当前结果列表中，则忽略
            if info_list in self.current_result:
                return

            display_info = "{:*^50}".format(" 【%s】总用时：%02d:%02d " % (self.date, h, m)) + " "*50 + "\n"
            display_info += '\n'.join(info_list[1:])
            display_info += "\n{:*^56}\n".format("")

            self.current_result.append(info_list)
            self.mail_mq.append(info_list[:])
            print(display_info)
            return

        current_stage_ways = self.global_result[stage]
        for index, way in enumerate(current_stage_ways):
            starttime = way[3]
            endtime = way[4]
            if endtime > starttime >= last_end_time:
                self.filter_global_result(stage + 1, endtime, history + [[stage, index]])


    def do_task(self, count):
        """
        执行指定索引的任务
        :param task_index:
        :return:
        """
        if not self.date:
            self.tf_log.error("请先指定date！")
            return False
        task_index = count % len(self.tasks)
        if task_index == 0:
            now = time.time()
            if self.last_round_time:
                self.interval = now - self.last_round_time
            else:
                self.interval = 0
            self.last_round_time = time.time()
            # 如果开启了自动缓存时间
            if count > 0 and self.auto_expire:
                expire_time_adjust = (self.interval - self.expire_time) / 10
                self.expire_time += expire_time_adjust
                self.expire_time = max(self.min_expire_time, self.expire_time)

        task = self.tasks[task_index]
        choose_cities_chinese = [self.transfer_cities[i] for i in task]
        display = '-'.join(choose_cities_chinese)
        try:
            cache_ratio = self.count_cache / (self.count_cache + self.count_online) * 100
        except:
            cache_ratio = 0
        print(f"【已查询{count//len(self.tasks)}轮 当前周期{round(self.interval, 2)}s 缓存时间{round(self.expire_time, 1)}s "
              f"缓存比{round(cache_ratio, 1)}%】正在查询 {display} 的换乘方案" + " " * 20, end='\r')

        self.global_result = []
        for i in range(len(task) - 1):
            from_station_name = self.transfer_cities[task[i]]
            to_station_name = self.transfer_cities[task[i + 1]]
            stage_result = self.get_tickets(from_station_name, to_station_name)
            self.global_result.append(stage_result)

        # 获取到某种换乘方案，计算可行的（时间能接上的）
        if [] not in self.global_result:
            self.filter_global_result()



class Database(object):
    """
    SQLite缓存数据库类
    """
    def __init__(self, db_path="./transfer.db"):
        self.db_log = logging.getLogger(__name__)
        if not os.path.exists(db_path):
            self.db_log.info("数据库不存在！")
            init_db = True
        else:
            self.db_log.info("数据库连接成功！")
            init_db = False

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = self.dict_factory
        self.cursor = self.conn.cursor()
        if init_db:
            self.init_transfer_db()


    def init_transfer_db(self):
        """
        第一次创建数据库时建立数据表
        :return:
        """
        init_sql = """
            create table transfer (
                code varchar(20) not null,
                from_date varchar(10) not null,
                from_city varchar(20) not null,
                arrive_city varchar(20) not null,
                from_code varchar(10) not null,
                from_time varchar(10) not null,
                arrive_code varchar(10) not null,
                arrive_time varchar(10) not null,
                update_time timestamp default (datetime('now','localtime')),
                has_ticket int(1) not null,
                constraint transfer_pk primary key (code, from_date, from_code, arrive_code)
            );"""
        self.cursor.execute(init_sql)
        self.db_log.info("数据库初始化成功！")


    def getall(self, sql, params=None):
        """
        查询所有记录，返回列表
        :param sql:
        :return:
        """
        if params:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        values = self.cursor.fetchall()
        return values


    def save(self, sql, params=None):
        """
        插入或删除记录
        :param sql:
        :param params:
        :return:
        """
        if params:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        self.conn.commit()
        return True


    def dict_factory(self, cursor, row):
        """
        返回字典类型的数据
        :param cursor:
        :param row:
        :return:
        """
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d



class Mail(object):
    """
    封装的邮件发送类
    """
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
