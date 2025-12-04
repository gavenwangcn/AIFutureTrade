"""
K线图表后端API服务 (Flask版本)
提供从akshare、tushare和baostock获取股票数据的接口
"""
import akshare as ak
import tushare as ts
import baostock as bs
import pandas as pd
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import logging
import traceback
import json
import atexit
import gc
import os
import time
from datetime import datetime, timedelta
from chinese_calendar import is_holiday
import re

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
# 配置CORS，允许所有来源、方法和请求头
CORS(app, origins="*", methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])

# 定义清理函数
def cleanup():
    """清理资源"""
    logger.info("正在清理资源...")
    # 强制进行垃圾回收
    gc.collect()
    logger.info("资源清理完成")

# 注册清理函数，在应用退出时调用
atexit.register(cleanup)

def is_trading_day(date):
    """
    判断指定日期是否为交易日
    参数:
        date: 日期对象
    返回:
        如果是交易日返回True，否则返回False
    """
    # 判断是否为周末或节假日
    if date.weekday() >= 5 or is_holiday(date):  # 5=Saturday, 6=Sunday
        return False
    
    return True

def get_last_trading_day():
    """
    获取最后一个交易日
    判断逻辑：
    1）交易日判断：是否周末或者节假日，如果不是，就是交易日；
    2）先计算今天是否是交易日，如果不是，那就计算前一天，直至交易日出现
    返回:
        最后一个交易日的日期对象
    """
    try:
        today = datetime.now().date()
        
        # 如果今天是交易日，直接返回
        if is_trading_day(today):
            return today
        
        # 如果今天不是交易日，向前查找最近的交易日
        current_date = today - timedelta(days=1)
        while not is_trading_day(current_date):
            current_date -= timedelta(days=1)
        
        return current_date
    except Exception as e:
        logger.warning(f"获取最后一个交易日时出错: {str(e)}")
        # 如果出现异常，返回昨天
        return datetime.now().date() - timedelta(days=1)

def is_local_file_up_to_date(file_path):
    """
    检查本地文件是否是最新的
    判断逻辑：
    1）判断文件最新修改时间和当前时间之间，是否存在交易时间。
    2）交易日判断：非节假日，非周末；
    3）交易时间：9:30～11:30，13:00～15:00
    4）特殊情况：如果不同的两天之间的交易日仅仅是当前这一天，那么当前时间在9:30之前，不算是交易日，9:30之后，算交易日
    参数:
        file_path: 文件路径
    返回:
        如果文件是最新的则返回True，否则返回False
    """
    try:
        # 获取文件的最后修改时间
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        
        # 获取当前时间
        now = datetime.now()
        
        # 如果文件是今天修改的
        if file_mod_time.date() == now.date():
            # 如果今天不是交易日，则文件是最新的
            if not is_trading_day(file_mod_time.date()):
                return True
            
            # 如果今天是交易日:
            file_time = file_mod_time.time()
            now_time = now.time()

            # 检查文件修改时间是否在交易时间之后,如果是：返回True
            if file_time >= datetime.strptime("15:00", "%H:%M").time():
                return True
            
            # 如果当前时间在上午交易时间之前
            if now_time <= datetime.strptime("09:30", "%H:%M").time():
                return True
            
            # 如果当前时间在下午交易时间之后，文件修改时间在下午交易时间或之前，
            if now_time > datetime.strptime("15:00", "%H:%M").time() and file_time <= datetime.strptime("15:00", "%H:%M").time():
                return False
            
            # 如果当前时间在交易时间,返回False
            if datetime.strptime("09:30", "%H:%M").time() <= now_time <= datetime.strptime("11:30", "%H:%M").time() and \
                datetime.strptime("11:30", "%H:%M").time() < now_time < datetime.strptime("13:00", "%H:%M").time():
                return False

        # 如果文件修改时间与当前时间不在同一天
        # 首先检查文件修改时间当天是否是交易日且在交易时间之后
        if is_trading_day(file_mod_time.date()):
            
            # 检查文件修改时间是否在交易时间之后
            file_time = file_mod_time.time()
            # 如果文件修改时间在下午交易时间或之后，则认为文件是当天最新的
            if file_time >= datetime.strptime("15:00", "%H:%M").time():
                # 继续检查跨天情况
                pass
            else:
                # 文件修改时间不在下午交易时间之后，则返回False
                return False
        
        # 检查从文件修改时间的第二天到当前日期之间是否有交易日
        current_date = file_mod_time.date() + timedelta(days=1)
        end_date = now.date()
        
        # 遍历这两天之间的所有日期
        while current_date <= end_date:
            if is_trading_day(current_date):
                # 如果存在交易日，则文件不是最新的
                return False
            current_date += timedelta(days=1)
        
        # 如果不存在交易日，则文件是最新的
        return True
    except Exception as e:
        logger.warning(f"检查文件是否最新时出错: {str(e)}")
        # 如果出现异常，返回False
        return False

def fetch_kline_data_from_tushare(symbol, period, data_type):
    """
    从tushare获取K线数据的函数。
    参数:
        symbol: 股票或指数代码
        period: 时间周期
        data_type: 数据类型 ('stock' 或 'index')
    返回:
        K线数据DataFrame
    """
    try:
        # 配置tushare token
        # 注意：在生产环境中，应该从环境变量或配置文件中读取token
        TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN')
        ts.set_token(TUSHARE_TOKEN)
        
        # 初始化tushare pro接口
        pro = ts.pro_api()
        
        # 处理股票代码格式
        # tushare要求股票代码格式为 XXXXXX.SH 或 XXXXXX.SZ
        if symbol.endswith('.SH') or symbol.endswith('.SZ'):
            ts_code = symbol
        elif symbol.startswith('6') or symbol == '000001':  # 上证指数特殊处理
            ts_code = f'{symbol}.SH'  # 上海证券交易所
        else:
            ts_code = f'{symbol}.SZ'  # 深圳证券交易所
        
        # 处理周期参数
        if period in ['daily', 'weekly', 'monthly']:
            # 对于日线、周线、月线数据，使用daily接口
            # tushare的daily接口支持通过freq参数指定频率
            freq_map = {
                'daily': 'D',
                'weekly': 'W',
                'monthly': 'M'
            }
            freq = freq_map.get(period, 'D')
            
            # 获取最近1000条数据
            kline_df = ts.pro_bar(ts_code=ts_code, adj='qfq', freq=freq, limit=1000)
            
            if kline_df is not None and not kline_df.empty:
                # 重命名列以匹配akshare的格式
                kline_df = kline_df.rename(columns={
                    'trade_date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'vol': '成交量'
                })
                
                # 转换日期格式
                kline_df['日期'] = pd.to_datetime(kline_df['日期'], format='%Y%m%d')
                kline_df['日期'] = kline_df['日期'].dt.strftime('%Y-%m-%d')
                
                # 按日期排序
                kline_df = kline_df.sort_values('日期').reset_index(drop=True)
                
                logger.info(f"从tushare获取到{len(kline_df)}条数据")
                return kline_df
        elif period in ['1', '5', '15', '30', '60']:
            # 对于分钟级别的数据，使用分钟线接口
            # 注意：tushare的分钟线数据可能需要不同的处理方式
            logger.warning(f"tushare暂不支持{period}分钟级别的数据获取")
            return None
        else:
            # 默认使用日线数据
            # kline_df = ts.pro_bar(ts_code=ts_code, adj='qfq', freq='D', limit=1000)
            kline_df = pro.index_daily(ts_code=ts_code)

            
            if kline_df is not None and not kline_df.empty:
                # 重命名列以匹配akshare的格式
                kline_df = kline_df.rename(columns={
                    'trade_date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'vol': '成交量'
                })
                
                # 转换日期格式
                kline_df['日期'] = pd.to_datetime(kline_df['日期'], format='%Y%m%d')
                kline_df['日期'] = kline_df['日期'].dt.strftime('%Y-%m-%d')
                
                # 按日期排序
                kline_df = kline_df.sort_values('日期').reset_index(drop=True)
                
                logger.info(f"从tushare获取到{len(kline_df)}条数据")
                return kline_df
        
        return None
    except Exception as e:
        logger.warning(f"调用tushare获取{data_type}历史数据时出错: {str(e)}, symbol: {symbol}, period: {period}")
        logger.warning(traceback.format_exc())
        return None

def fetch_kline_data_from_akshare(symbol, period, data_type):
    """
    从akshare获取K线数据的函数
    参数:
        symbol: 股票或指数代码
        period: 时间周期
        data_type: 数据类型 ('stock' 或 'index')
    返回:
        K线数据DataFrame
    """
    kline_df = None
    
    try:
        if data_type == 'index':
            if period in ['1', '5', '15', '30', '60']:
                # 分钟级别的数据使用index_zh_a_hist_min_em函数
                akshare_period = period
                kline_df = ak.index_zh_a_hist_min_em(symbol=symbol, period=akshare_period)
                logger.info(f"调用ak.index_zh_a_hist_min_em获取到数据: {len(kline_df) if kline_df is not None else 0}条")
            elif period in ['daily', 'weekly', 'monthly']:
                # 日线/周线/月线数据使用index_zh_a_hist函数
                # 注意：index_zh_a_hist函数不支持adjust参数
                kline_df = ak.index_zh_a_hist(symbol=symbol, period=period)
                logger.info(f"调用ak.index_zh_a_hist获取到数据: {len(kline_df) if kline_df is not None else 0}条")
            else:
                # 默认使用日线数据
                kline_df = ak.index_zh_a_hist(symbol=symbol, period="daily")
                logger.info(f"调用ak.index_zh_a_hist(默认)获取到数据: {len(kline_df) if kline_df is not None else 0}条")
        else:  # stock
            if period in ['1', '5', '15', '30', '60']:
                # 分钟级别的数据使用stock_zh_a_hist_min_em函数
                akshare_period = period
                kline_df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=akshare_period, adjust="qfq")
                logger.info(f"调用ak.stock_zh_a_hist_min_em获取到数据: {len(kline_df) if kline_df is not None else 0}条")
            elif period in ['daily', 'weekly', 'monthly']:
                # 日线/周线/月线数据使用stock_zh_a_hist函数
                kline_df = ak.stock_zh_a_hist(symbol=symbol, period=period, adjust="qfq")
                logger.info(f"调用ak.stock_zh_a_hist获取到数据: {len(kline_df) if kline_df is not None else 0}条")
            else:
                # 默认使用日线数据
                kline_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
                logger.info(f"调用ak.stock_zh_a_hist(默认)获取到数据: {len(kline_df) if kline_df is not None else 0}条")
    except Exception as e:
        logger.warning(f"调用akshare获取{data_type}历史数据时出错: {str(e)}, symbol: {symbol}, period: {period}")
        logger.warning(traceback.format_exc())
        kline_df = None
    
    return kline_df

def fetch_kline_data_from_baostock(symbol, period, data_type):
    """
    从baostock获取K线数据的函数。

    参数:
        symbol: 股票或指数代码
        period: 时间周期
        data_type: 数据类型 ('stock' 或 'index')
    返回:
        K线数据DataFrame
    """
    try:
        # 登录baostock
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"登录baostock失败: {lg.error_msg}")
            return None
        
        # 处理股票代码格式
        # baostock要求股票代码格式为 sh.XXXXXX 或 sz.XXXXXX
        if symbol.startswith('sh.') or symbol.startswith('sz.'):
            bs_code = symbol
        elif symbol.startswith('6') or symbol == '000001':  # 上证指数特殊处理
            bs_code = f'sh.{symbol}'  # 上海证券交易所
        else:
            bs_code = f'sz.{symbol}'  # 深圳证券交易所
        
        # 处理周期参数
        if period in ['daily', 'weekly', 'monthly']:
            # 对于日线、周线、月线数据
            freq_map = {
                'daily': 'd',
                'weekly': 'w',
                'monthly': 'm'
            }
            freq = freq_map.get(period, 'd')
            
            # 获取最近1000条数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume",
                start_date='',
                end_date='',
                frequency=freq,
                adjustflag='3'  # 后复权
            )
            
            # 检查错误码
            if rs.error_code != '0':
                logger.warning(f"baostock查询数据失败: {rs.error_msg}")
                return None
            
            # 获取数据
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            # 转换为DataFrame
            if data_list:
                kline_df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 重命名列以匹配统一格式
                kline_df = kline_df.rename(columns={
                    'date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'volume': '成交量'
                })
                
                # 转换数据类型
                kline_df[['开盘', '最高', '最低', '收盘', '成交量']] = kline_df[['开盘', '最高', '最低', '收盘', '成交量']].astype(float)
                
                # 按日期排序
                kline_df = kline_df.sort_values('日期').reset_index(drop=True)
                
                logger.info(f"从baostock获取到{len(kline_df)}条数据")
                return kline_df
        elif period in ['1', '5', '15', '30', '60']:
            # 对于分钟级别的数据
            freq_map = {
                '1': '1',
                '5': '5',
                '15': '15',
                '30': '30',
                '60': '60'
            }
            freq = freq_map.get(period, '1')
            
            # 获取最近1000条数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,time,code,open,high,low,close,volume",
                start_date='',
                end_date='',
                frequency=freq,
                adjustflag='3'  # 后复权
            )
            
            # 检查错误码
            if rs.error_code != '0':
                logger.warning(f"baostock查询数据失败: {rs.error_msg}")
                return None
            
            # 获取数据
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            # 转换为DataFrame
            if data_list:
                kline_df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 重命名列以匹配统一格式
                kline_df = kline_df.rename(columns={
                    'time': '时间',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'volume': '成交量'
                })
                
                # 转换数据类型
                kline_df[['开盘', '最高', '最低', '收盘', '成交量']] = kline_df[['开盘', '最高', '最低', '收盘', '成交量']].astype(float)
                
                # 按时间排序
                kline_df = kline_df.sort_values('时间').reset_index(drop=True)
                
                logger.info(f"从baostock获取到{len(kline_df)}条数据")
                return kline_df
        else:
            # 默认使用日线数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume",
                start_date='',
                end_date='',
                frequency='d',
                adjustflag='3'  # 后复权
            )
            
            # 检查错误码
            if rs.error_code != '0':
                logger.warning(f"baostock查询数据失败: {rs.error_msg}")
                return None
            
            # 获取数据
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            # 转换为DataFrame
            if data_list:
                kline_df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 重命名列以匹配统一格式
                kline_df = kline_df.rename(columns={
                    'date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'volume': '成交量'
                })
                
                # 转换数据类型
                kline_df[['开盘', '最高', '最低', '收盘', '成交量']] = kline_df[['开盘', '最高', '最低', '收盘', '成交量']].astype(float)
                
                # 按日期排序
                kline_df = kline_df.sort_values('日期').reset_index(drop=True)
                
                logger.info(f"从baostock获取到{len(kline_df)}条数据")
                return kline_df
        
        return None
    except Exception as e:
        logger.warning(f"调用baostock获取{data_type}历史数据时出错: {str(e)}, symbol: {symbol}, period: {period}")
        logger.warning(traceback.format_exc())
        return None
    finally:
        # 登出baostock
        bs.logout()

def fetch_kline_data(symbol, period, data_type, data_source='tushare'):
    """
    获取K线数据的通用函数
    参数:
        symbol: 股票或指数代码
        period: 时间周期
        data_type: 数据类型 ('stock' 或 'index')
        data_source: 数据源 ('akshare'、'tushare' 或 'baostock')
    返回:
        K线数据列表
    """
    # 初始化数据框
    kline_df = None
    
    # 构造本地文件路径
    local_file_path = f"../datas/{symbol}_{period}_{data_type}.csv"
    logger.info(f"处理{data_type}数据请求: symbol={symbol}, period={period}, local_file_path={local_file_path}")
    
    # 检查本地是否存在数据文件
    if os.path.exists(local_file_path):
        # 检查文件是否是最新的（24小时内）
        if is_local_file_up_to_date(local_file_path):
            # 读取本地数据
            logger.info(f"读取本地缓存数据: {local_file_path}")
            kline_df = pd.read_csv(local_file_path)
            logger.info(f"从本地缓存读取到{len(kline_df)}条数据")
        else:
            logger.info(f"本地缓存数据已过期: {local_file_path}")
    else:
        logger.info(f"本地缓存文件不存在: {local_file_path}")
    
    # 如果没有本地数据或数据已过期，则从数据源获取
    if kline_df is None:
        logger.info(f"从{data_source}获取{data_type}数据: symbol={symbol}, period={period}")
        try:
            if data_source == 'tushare':
                # 从tushare获取数据
                kline_df = fetch_kline_data_from_tushare(symbol, period, data_type)
            elif data_source == 'baostock':
                # 从baostock获取数据
                kline_df = fetch_kline_data_from_baostock(symbol, period, data_type)
            else:
                # 从akshare获取数据
                kline_df = fetch_kline_data_from_akshare(symbol, period, data_type)
            
            # 保存数据到本地
            if kline_df is not None and not kline_df.empty:
                # 先删除原有的缓存文件
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)
                    logger.info(f"已删除原有缓存文件: {local_file_path}")
                # 保存新的数据
                kline_df.to_csv(local_file_path, index=False)
                logger.info(f"已保存数据到本地: {local_file_path}, 共{len(kline_df)}条数据")
            else:
                logger.warning(f"从{data_source}获取到的{data_type}数据为空: symbol={symbol}, period={period}")
        except Exception as e:
            logger.warning(f"调用{data_source}获取{data_type}历史数据时出错: {str(e)}, symbol: {symbol}, period: {period}")
            logger.warning(traceback.format_exc())
            kline_df = None

    # 检查返回的数据是否为None
    if kline_df is None or kline_df.empty:
        logger.warning(f"获取到的{data_type}数据为None或为空, symbol: {symbol}, period: {period}")
        raise ValueError(f"「{symbol}」未找到指定{data_type}的历史数据")
    
    # 转换数据格式
    return convert_kline_data(kline_df, data_type)

def convert_kline_data(df, datatype):
    """
    将K线数据转换为统一格式
    参数:
        df: 包含K线数据的DataFrame
        data_type: 数据类型 ('stock' 或 'index')
    返回:
        转换后的K线数据列表
    """
    # 检查数据框中的列名
    if '时间' in df.columns:
        # 分钟数据
        # 将本地时间（中国时区）转换为UTC时间戳
        datetime_series = pd.to_datetime(df['时间'])
        # 检查是否已经有时区信息
        if datetime_series.dt.tz is None:
            # 如果没有时区信息，添加中国时区
            timestamp_series = datetime_series.dt.tz_localize('Asia/Shanghai')
        else:
            # 如果已经有时间信息，直接使用
            timestamp_series = datetime_series
        # 转换为UTC时区并生成时间戳
        df['timestamp'] = timestamp_series.dt.tz_convert('UTC').astype('int64') // 10**9 * 1000
    elif '日期' in df.columns:
        # 日线数据
        # 将本地日期转换为UTC时间戳（设置为当天00:00:00）
        date_series = pd.to_datetime(df['日期'])
        # 检查是否已经有时区信息
        if date_series.dt.tz is None:
            # 如果没有时区信息，添加中国时区
            timestamp_series = date_series.dt.tz_localize('Asia/Shanghai')
        else:
            # 如果已经有时间信息，直接使用
            timestamp_series = date_series
        # 转换为UTC时区并生成时间戳
        df['timestamp'] = timestamp_series.dt.tz_convert('UTC').astype('int64') // 10**9 * 1000
    else:
        raise ValueError("数据格式不正确")
    
    # 统一处理返回数据
    kline_data = df[['timestamp', '开盘', '最高', '最低', '收盘', '成交量']].rename(columns={
        '开盘': 'open',
        '最高': 'high',
        '最低': 'low',
        '收盘': 'close',
        '成交量': 'volume'
    }).to_dict('records')
    
    return kline_data

@app.route('/')
def read_root():
    """
    根路径端点
    用于测试API服务是否正常运行
    """
    response_data = {"message": "K线图表API服务正常运行"}
    return Response(json.dumps(response_data, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    """
    获取A股股票代码列表
    返回所有A股股票的代码和名称
    """
    
    try:
        logger.info("准备获取自选股的股票代码列表...")
        # 从CSV文件读取数据
        import csv
        symbols = []
        with open('symbols.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                symbols.append({
                    "ticker": row['ticker'],
                    "name": row['name'],
                    "exchange": row['exchange'],
                    "type": row['type'],
                    "priceCurrency": row['priceCurrency']
                })
        
        logger.info("成功获取股票数据，准备返回...")
        logger.debug(f"返回的数据: {symbols}")
        
        return Response(json.dumps(symbols, ensure_ascii=False), mimetype='application/json; charset=utf-8')
    except Exception as e:
        logger.error(f"获取股票数据时发生错误: {str(e)}")
        logger.error(f"错误类型: {type(e)}")
        logger.error(traceback.format_exc())
        error_response = {"error": "获取股票数据时发生错误"}
        return Response(json.dumps(error_response, ensure_ascii=False), mimetype='application/json; charset=utf-8'), 500

# 添加路由
@app.route('/api/history_kline', methods=['POST'])
def get_history_kline():
    """
    获取指定股票或指数的历史K线数据
    参数:
        symbol: 股票或指数代码
        period: 时间周期 (1, 5, 15, 30, 60, daily, weekly, monthly)
        type: 类型 (stock-股票, index-指数)
    返回:
        指定股票或指数的历史K线数据
    """
    try:
        # 获取请求数据
        data = request.get_json()
        symbol = data.get('symbol')
        period = data.get('period', 'daily')  # 默认为日线
        data_type = data.get('type', 'stock')  # 默认为股票
        data_source = data.get('data_source', 'baostock')  # 默认为baostock
        
        # 验证period参数
        valid_periods = ['1', '5', '15', '30', '60', 'daily', 'weekly', 'monthly']
        if period not in valid_periods:
            period = 'daily'  # 如果参数无效，则默认为日线
        
        if not symbol:
            return jsonify({"error": "缺少代码参数"}), 400
        
        # 处理带交易所后缀的代码
        # 例如：'000001.SH' 转换为 '000001'
        if '.' in symbol:
            symbol = symbol.split('.')[0]
        
        # 根据type参数选择调用的函数
        kline_data = fetch_kline_data(symbol, period, data_type, data_source)
        
        response_data = {"symbol": symbol, "period": period, "data": kline_data}
        return Response(json.dumps(response_data, ensure_ascii=False), mimetype='application/json; charset=utf-8')
    except ValueError as e:
        # 处理数据未找到的情况
        logger.warning(str(e))
        error_response = {"error": str(e)}
        return Response(json.dumps(error_response, ensure_ascii=False), mimetype='application/json; charset=utf-8'), 404
    except Exception as e:
        logger.error(f"获取{data_type}{symbol}历史K线数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        error_response = {"error": f"获取{data_type}{symbol}历史K线数据失败: {str(e)}"}
        return Response(json.dumps(error_response, ensure_ascii=False), mimetype='application/json; charset=utf-8'), 500

# 添加在Flask应用初始化之后
# 增强日志配置细节
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(module)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 增强全局异常处理
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error("未捕获异常: %s", str(e), exc_info=True)
    error_response = {"error": f"服务器错误: {str(e)}"}
    return Response(json.dumps(error_response, ensure_ascii=False), mimetype='application/json; charset=utf-8'), 500

# 在get_symbols函数前添加请求日志
@app.before_request
def log_request_info():
    logger.info(f"收到请求: {request.method} {request.path}")

# 启动Flask应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
