import time
from operator import itemgetter
from transfer import Transfer, Mail
from config import *


print("\n# {:*^90} #".format(""))
print("# {:^80} #".format(" 欢迎使用12306余票查询服务 "))
print("# {:^90} #".format(" Author: yuanyuanzijin "))
print("# {:^90} #".format(f" Version: {Transfer.__tf_version__} - {Transfer.__update_time__} "))
print("# {:*^90} #\n".format(""))

tf = Transfer(date=DATE, transfer_cities=TRANSFER_CITIES, max_transfer_times=MAX_TRANSFER,
              expect_total_time=EXPECT_TOTAL_TIME, retry_times=RETRY_TIMES, expire_time=EXPIRE_TIME,
              min_expire_time=MIN_EXPIRE_TIME, auto_expire=AUTO_EXPIRE)

print('\n')
print("{:*^50}".format(" 任务信息如下 "))
print(f"出发日期：{DATE}")
print(f"始发城市：{TRANSFER_CITIES[0]}")
print(f"终到城市：{TRANSFER_CITIES[-1]}")
print(f"可选换乘城市：{', '.join(TRANSFER_CITIES[1:-1])}")
print(f"最大换乘次数：{MAX_TRANSFER}")
print(f"期望总时间：<{EXPECT_TOTAL_TIME}h")
print("{:*^56}".format(""))
print(f"理论换乘路线：{len(tf.tasks)}个")
print(f"初始缓存时间：{EXPIRE_TIME}s")
print(f"最小缓存时间：{MIN_EXPIRE_TIME}s")
print(f"邮件最小间隔：{MAIL_MIN_INTERVAL}s")
print(f"邮件通知：{'开启' if EMAIL_ENABLE else '关闭'}")
print(f"通知邮箱：{RECEIVE_EMAIL}")
print(f"最大重试：{RETRY_TIMES}次")
print("{:*^56}".format(""))
print('\n')

if EMAIL_ENABLE:
    content = f"出发日期：{DATE}<br />" \
              f"始发城市：{TRANSFER_CITIES[0]}<br />" \
              f"终到城市：{TRANSFER_CITIES[-1]}<br />" \
              f"可选换乘城市：{', '.join(TRANSFER_CITIES[1:-1])}<br />" \
              f"最大换乘次数：{MAX_TRANSFER}<br />" \
              f"期望总时间：<{EXPECT_TOTAL_TIME}h<hr />" \
              f"Powered by ZijinAI<br />" \
              f"https://github.com/yuanyuanzijin"
    mail = Mail(mail_host=MAIL_HOST, mail_port=MAIL_PORT, mail_user=MAIL_USER, mail_pass=MAIL_PASS,
                sender_name=SENDER_NAME, email_addr=RECEIVE_EMAIL)
    mail.send_mail(subject="余票查询服务已启动", content=content)


# 开始任务
count = 0
last_mail_time = time.time()
while True:
    # 执行查票任务
    tf.do_task(count)
    count += 1

    # 不需要发邮件则跳过
    if not EMAIL_ENABLE:
        continue

    # 如果距离上一次发邮件超过最小邮件间隔
    ctime = time.time()
    if ctime - last_mail_time > MAIL_MIN_INTERVAL:
        last_mail_time = time.time()
        send_list = []

        # 获取发送队列
        while tf.mail_mq:
            send_list.append(tf.mail_mq.pop(0))

        # 没有新方案则跳过
        if not send_list:
            continue

        # 按照总用时排序
        send_list.sort(key=lambda x: itemgetter(1, 2)(x[0]))
        mail_content = "为您找到%d个换乘方案" % len(send_list)
        for line in send_list:
            date, h, m = line.pop(0)
            line_display = "<br /><br />{:*^20}<br />".format(" 【%s】总用时：%02d:%02d " % (date, h, m))
            line_display += '<br />'.join(line)
            mail_content += line_display
        mail.send_mail(subject="为您找到换乘方案", content=mail_content)
