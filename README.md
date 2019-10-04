# 12306任意次换乘方案查询

12306换乘方案查询，官方只提供一次换乘的查询，通过本程序可以查询任意次换乘的方案。

![终端启动页面](https://github.com/yuanyuanzijin/12306-transfer/raw/master/imgs/1.png)

![终端查询结果页面](https://github.com/yuanyuanzijin/12306-transfer/raw/master/imgs/2.png)

![手机邮件通知](https://github.com/yuanyuanzijin/12306-transfer/raw/master/imgs/3.png)

![手机邮件通知](https://github.com/yuanyuanzijin/12306-transfer/raw/master/imgs/4.png)

## 配置

1. 运行环境：Python 3.7

2. 安装依赖：requests

    ```
    pip install requests
    ```
  
## 使用方法

1. 下载代码至本地

    ```
   git clone https://github.com/yuanyuanzijin/12306-transfer
   ```

2. 复制config.py.example为config.py，修改其中的配置

3. 在根目录下执行

    ```
    python index.py
    ```
   
## 技术概览

* 爬虫：从12306获取余票信息，这里有一个坑，只在POST请求中放入查询的信息是不行的，还需要将查询信息提前写入Cookies，否则经常返回错误。（注意是经常，不是一定，明明发现你是爬虫，却不100%封掉，给你留10%通过，这是最可怕的）

* DFS：面对不同段的余票信息，需计算时间可行的方案，这里需要用到深度优先遍历

* 缓存：使用sqlite3数据库提高信息利用率，缓存时间可配

* 队列：为邮件发送任务设立队列，并使用最小发送时间控制，使一封邮件可以发送多条信息

* 缓存时间可自动调整

## 版本历史

* 【2.0】2019/10/04 优化，支持邮件发送

* 【1.0】2019/10/03 使用类，加入缓存机制

* 【0.1】2019/10/01 基本功能实现（爬虫、DFS部分）

## About

Louie Jin - yuanyuanzijin@gmail.com

[https://github.com/yuanyuanzijin][url]

Powered by ZijinAI


[url]: https://github.com/yuanyuanzijin