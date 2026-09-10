#coding:gbk
# T+0网格做T策略 - 26~30元区间版 (大QMT内置策略版)
# 运行周期: 分笔(tick)
# 标的: 300302.SZ 同有科技

import datetime

# ============================================================
#  配置区
# ============================================================
CONFIG = {
    'stock_code': '300302.SZ',
    'account_id': '',
    'base_buy_price': 26.00,
    'base_sell_price': 26.20,
    'min_buy_price': 26.00,
    'max_sell_price': 30.00,
    'grid_interval': 0.10,
    'buy_order_count': 3,
    'sell_order_count': 3,
    'buy_volume': 100,
    'sell_volume': 100,
    'max_warp': 3,
    'end_restore': True,
    'restore_time': '14:50:00',
    'breakout_mode': 'extend',
    'extend_max_sell': 24.00,
    'extend_interval': 0.20,
}


# ============================================================
#  全局状态容器
# ============================================================
class G:
    inited = False
    active_orders = {}
    buy_traded_count = 0
    sell_traded_count = 0
    initial_position = 0
    cur_buy_base = 0.0
    cur_sell_base = 0.0
    cur_min_buy = 0.0
    cur_max_sell = 0.0
    cur_interval = 0.0
    cur_buy_count = 0
    cur_sell_count = 0
    breakout_triggered = False
    above_ticks = 0
    position_restored = False
    last_order_check = ''


def _round(p):
    return round(p, 2)

def _now():
    return datetime.datetime.now().strftime('%H:%M:%S')

def _log(msg):
    print('[%s] %s' % (_now(), msg))

def _acc():
    return CONFIG['account_id']


# ============================================================
#  init
# ============================================================
def init(ContextInfo):
    G.inited = False
    G.active_orders = {}
    G.buy_traded_count = 0
    G.sell_traded_count = 0
    G.breakout_triggered = False
    G.above_ticks = 0
    G.position_restored = False

    G.cur_min_buy = CONFIG['min_buy_price']
    G.cur_max_sell = CONFIG['max_sell_price']
    G.cur_interval = CONFIG['grid_interval']
    G.cur_buy_count = CONFIG['buy_order_count']
    G.cur_sell_count = CONFIG['sell_order_count']
    G.cur_buy_base = CONFIG['base_buy_price']
    G.cur_sell_base = CONFIG['base_sell_price']

    # 设置交易账号（大QMT必须，否则passorder返回0）
    acc = _acc()
    if acc:
        try:
            ContextInfo.set_account(acc)
            _log('set_account: %s' % acc)
        except Exception as e:
            _log('set_account failed: %s' % str(e))

    _log('init ok: %s buy=%.2f sell=%.2f interval=%.2f' % (
        CONFIG['stock_code'], G.cur_buy_base, G.cur_sell_base, G.cur_interval))


# ============================================================
#  handlebar
# ============================================================
def handlebar(ContextInfo):
    stock = CONFIG['stock_code']

    if not G.inited:
        G.initial_position = _get_position(ContextInfo, stock)
        _log('initial position: %d shares' % G.initial_position)

        # 动态调整: 以当前价为中心设置网格
        current_price = _get_last_price(ContextInfo, stock)
        if current_price > 0:
            G.cur_buy_base = _round(current_price - CONFIG['grid_interval'])
            G.cur_sell_base = _round(current_price + CONFIG['grid_interval'])
            G.cur_min_buy = _round(current_price - 1.00)
            G.cur_max_sell = _round(current_price + 1.00)
            _log('auto adjust: price=%.2f buy=%.2f sell=%.2f range=%.2f~%.2f' % (
                current_price, G.cur_buy_base, G.cur_sell_base,
                G.cur_min_buy, G.cur_max_sell))
        else:
            _log('warning: cannot get current price, use default')

        _place_grid_orders(ContextInfo)
        G.inited = True
        return

    if G.position_restored:
        return

    price = _get_last_price(ContextInfo, stock)
    if price <= 0:
        return

    _check_orders(ContextInfo)

    if not G.breakout_triggered:
        _check_breakout(ContextInfo, price)

    _check_warp(ContextInfo)
    _check_restore(ContextInfo)


# ============================================================
#  行情获取
# ============================================================
def _get_last_price(ContextInfo, stock):
    try:
        # 大QMT内置策略: get_full_tick获取分笔数据, 支持lastPrice
        tick = ContextInfo.get_full_tick([stock])
        if tick and stock in tick:
            return float(tick[stock]['lastPrice'])
    except:
        pass
    try:
        # 备用1: get_market_data用close字段(分笔close=最新价)
        data = ContextInfo.get_market_data(['close'], [stock], '')
        if data and stock in data:
            return float(data[stock]['close'])
    except:
        pass
    try:
        # 备用2: get_last_price函数
        return float(ContextInfo.get_last_price(stock))
    except:
        return 0.0


# ============================================================
#  持仓查询
# ============================================================
def _get_position(ContextInfo, stock):
    # 返回总持仓
    pos = _get_position_detail(ContextInfo, stock)
    return pos['total']

def _get_available(ContextInfo, stock):
    # 返回可用数量(可卖出, T+1后可用)
    pos = _get_position_detail(ContextInfo, stock)
    return pos['available']

def _get_position_detail(ContextInfo, stock):
    # 大QMT持仓查询: get_trade_detail_data(账号, 'stock', 'POSITION')
    # 注意参数顺序: 第二个是'stock', 第三个是'POSITION'
    result = {'total': 0, 'available': 0}
    acc = _acc()
    try:
        positions = get_trade_detail_data(acc, 'stock', 'POSITION')
        if positions:
            for p in positions:
                code = getattr(p, 'm_strInstrumentID', '') or getattr(p, 'stock_code', '')
                if code and (code == stock or code == stock.replace('.SZ', '').replace('.SH', '')):
                    result['total'] = int(getattr(p, 'm_nVolume', 0) or getattr(p, 'volume', 0))
                    # 可用数量: m_nCanUseVolume(挂卖单后会冻结, 撤单后恢复)
                    avail = getattr(p, 'm_nCanUseVolume', 0)
                    result['available'] = int(avail) if avail else 0
                    _log('position: total=%d available=%d' % (result['total'], result['available']))
                    return result
    except Exception as e:
        _log('get_position error: %s' % str(e))
    return result


# ============================================================
#  下单
# ============================================================
def _order(ContextInfo, direction, price, volume, remark=''):
    stock = CONFIG['stock_code']
    op_type = 23 if direction == 'buy' else 24  # 23=买入, 24=卖出
    order_type = 1101  # 1101=按股数下单

    if price > 0:
        pr_type = 11  # 11=限价
        model_price = float(price)
    else:
        pr_type = 5   # 5=最新价(市价)
        model_price = 0.0

    try:
        # 账号传空字符串, 让QMT使用模型交易中策略绑定的默认账号
        order_id = passorder(
            op_type,        # 23买/24卖
            order_type,     # 1101按股数
            '',             # 资金账号(空=用策略绑定账号)
            stock,          # 证券代码
            pr_type,        # 11限价/5最新价
            model_price,    # 委托价格
            float(volume),  # 委托数量
            'grid_t0',      # 策略名称
            2,              # quickTrade=2任何情况都执行
            ContextInfo     # 上下文对象
        )
        _log('debug passorder: op=%d otype=%d acc=empty code=%s pr=%d price=%.2f vol=%d ret=%s type=%s' % (
            op_type, order_type, stock, pr_type, model_price, volume,
            str(order_id), type(order_id).__name__))
        # 大QMT中passorder返回0也可能是委托已提交(订单号异步生成)
        # 只要没有异常就认为提交成功, 后续通过_check_orders查询实际状态
        _log('%s order price=%.2f vol=%d ret=%s %s' % (
            'BUY' if direction == 'buy' else 'SELL',
            price if price > 0 else 0, volume, str(order_id), remark))
        return order_id if order_id else -1  # -1表示已提交但ID未生成
    except Exception as e:
        _log('order error: %s' % str(e))
        return 0


# ============================================================
#  撤单
# ============================================================
def _cancel_order(ContextInfo, order_id):
    try:
        ContextInfo.cancel_order(order_id)
        _log('cancel order id=%d' % order_id)
        return True
    except:
        pass
    try:
        passorder(25, CONFIG['stock_code'], 13, -1, 0,
                  'grid_cancel', ContextInfo, 1, _acc())
        return True
    except Exception as e:
        _log('cancel error: %s' % str(e))
        return False


def _cancel_all(ContextInfo):
    for oid in list(G.active_orders.keys()):
        _cancel_order(ContextInfo, oid)
    G.active_orders.clear()


# ============================================================
#  挂网格委托
# ============================================================
def _place_grid_orders(ContextInfo):
    stock = CONFIG['stock_code']
    _cancel_all(ContextInfo)

    for i in range(G.cur_buy_count):
        price = _round(G.cur_buy_base - i * G.cur_interval)
        if price < G.cur_min_buy:
            break
        oid = _order(ContextInfo, 'buy', price, CONFIG['buy_volume'], 'buy_%d' % i)
        if oid:
            G.active_orders[oid] = {
                'price': price, 'volume': CONFIG['buy_volume'],
                'direction': 'buy', 'idx': i, 'status': 'pending'}

    # 卖单: 根据可用持仓数量调整笔数(T+1限制)
    available = _get_available(ContextInfo, stock)
    max_sell_orders = min(G.cur_sell_count, available // CONFIG['sell_volume'])
    if max_sell_orders < G.cur_sell_count:
        _log('available=%d, reduce sell orders %d->%d' % (
            available, G.cur_sell_count, max_sell_orders))

    for i in range(max_sell_orders):
        price = _round(G.cur_sell_base + i * G.cur_interval)
        if price > G.cur_max_sell:
            break
        oid = _order(ContextInfo, 'sell', price, CONFIG['sell_volume'], 'sell_%d' % i)
        if oid:
            G.active_orders[oid] = {
                'price': price, 'volume': CONFIG['sell_volume'],
                'direction': 'sell', 'idx': i, 'status': 'pending'}

    _log('grid placed: buy%d(%.2f) sell%d(%.2f) interval=%.2f' % (
        G.cur_buy_count, G.cur_buy_base,
        max_sell_orders, G.cur_sell_base, G.cur_interval))


# ============================================================
#  成交补单
# ============================================================
def _on_traded(ContextInfo, order_id):
    if order_id not in G.active_orders:
        return
    info = G.active_orders.pop(order_id)

    if info['direction'] == 'buy':
        G.buy_traded_count += 1
        G.cur_buy_base = _round(G.cur_buy_base - G.cur_interval)
        _log('BUY traded price=%.2f buy_base->%.2f' % (info['price'], G.cur_buy_base))
        _refill_order(ContextInfo, 'buy')
    else:
        G.sell_traded_count += 1
        G.cur_sell_base = _round(G.cur_sell_base + G.cur_interval)
        _log('SELL traded price=%.2f sell_base->%.2f' % (info['price'], G.cur_sell_base))
        _refill_order(ContextInfo, 'sell')


def _refill_order(ContextInfo, direction):
    if direction == 'buy':
        price = _round(G.cur_buy_base - (G.cur_buy_count - 1) * G.cur_interval)
        if price >= G.cur_min_buy:
            oid = _order(ContextInfo, 'buy', price, CONFIG['buy_volume'], 'buy_refill')
            if oid:
                G.active_orders[oid] = {
                    'price': price, 'volume': CONFIG['buy_volume'],
                    'direction': 'buy', 'idx': -1, 'status': 'pending'}
    else:
        price = _round(G.cur_sell_base + (G.cur_sell_count - 1) * G.cur_interval)
        if price <= G.cur_max_sell:
            oid = _order(ContextInfo, 'sell', price, CONFIG['sell_volume'], 'sell_refill')
            if oid:
                G.active_orders[oid] = {
                    'price': price, 'volume': CONFIG['sell_volume'],
                    'direction': 'sell', 'idx': -1, 'status': 'pending'}


# ============================================================
#  委托状态检查
# ============================================================
def _check_orders(ContextInfo):
    if not G.active_orders:
        return

    now_str = _now()
    if G.last_order_check == now_str:
        return
    G.last_order_check = now_str

    try:
        stock = CONFIG['stock_code']
        orders = ContextInfo.get_order_detail_data(stock, _acc(), 'stock')
        if not orders:
            return

        order_status = {}
        for o in orders:
            oid = getattr(o, 'order_id', None) or getattr(o, 'order_sysid', None)
            status = getattr(o, 'status', None)
            traded_vol = getattr(o, 'traded_volume', 0)
            order_vol = getattr(o, 'order_volume', 0)
            if oid:
                order_status[oid] = {
                    'status': status,
                    'traded': traded_vol,
                    'total': order_vol,
                    'done': (traded_vol >= order_vol and order_vol > 0)
                }

        for oid in list(G.active_orders.keys()):
            if oid in order_status:
                st = order_status[oid]
                if st['done']:
                    _on_traded(ContextInfo, oid)
                elif st['status'] in (5, 6, 7, 8):
                    G.active_orders.pop(oid, None)
    except:
        pass


# ============================================================
#  突破检测
# ============================================================
def _check_breakout(ContextInfo, price):
    if price >= G.cur_max_sell:
        G.above_ticks += 1
    else:
        G.above_ticks = max(0, G.above_ticks - 1)

    if G.above_ticks >= 20:
        G.breakout_triggered = True
        _log('BREAKOUT! price=%.2f >= %.2f' % (price, G.cur_max_sell))
        _apply_breakout_params(ContextInfo, price)


def _apply_breakout_params(ContextInfo, breakout_price):
    mode = CONFIG['breakout_mode']

    if mode == 'shift':
        offset = 2.00
        new_params = {
            'min_buy': _round(G.cur_min_buy + offset),
            'max_sell': _round(G.cur_max_sell + offset),
            'interval': G.cur_interval,
            'buy_count': G.cur_buy_count,
            'sell_count': G.cur_sell_count,
            'buy_base': _round(breakout_price),
            'sell_base': _round(breakout_price + G.cur_interval),
        }
    else:
        new_params = {
            'min_buy': G.cur_min_buy,
            'max_sell': _round(breakout_price + 3.00),
            'interval': CONFIG['extend_interval'],
            'buy_count': 2,
            'sell_count': 4,
            'buy_base': _round(breakout_price - CONFIG['extend_interval']),
            'sell_base': _round(breakout_price),
        }

    _log('breakout params(%s): %s' % (mode, str(new_params)))

    G.cur_min_buy = new_params['min_buy']
    G.cur_max_sell = new_params['max_sell']
    G.cur_interval = new_params['interval']
    G.cur_buy_count = new_params['buy_count']
    G.cur_sell_count = new_params['sell_count']
    G.cur_buy_base = new_params['buy_base']
    G.cur_sell_base = new_params['sell_base']

    _place_grid_orders(ContextInfo)


# ============================================================
#  风控
# ============================================================
def _check_warp(ContextInfo):
    warp = G.buy_traded_count - G.sell_traded_count
    if abs(warp) >= CONFIG['max_warp']:
        target = 'buy' if warp > 0 else 'sell'
        _log('RISK warp: %s count diff=%d>=%d, cancel all %s' % (
            'BUY' if warp > 0 else 'SELL', abs(warp), CONFIG['max_warp'], target))
        for oid, info in list(G.active_orders.items()):
            if info['direction'] == target:
                _cancel_order(ContextInfo, oid)
                G.active_orders.pop(oid, None)


# ============================================================
#  收盘复原
# ============================================================
def _check_restore(ContextInfo):
    if not CONFIG['end_restore'] or G.position_restored:
        return

    now_str = _now()
    if now_str >= CONFIG['restore_time']:
        G.position_restored = True
        _log('RESTORE at %s' % now_str)
        _cancel_all(ContextInfo)

        cur_pos = _get_position(ContextInfo, CONFIG['stock_code'])
        diff = cur_pos - G.initial_position

        if diff == 0:
            _log('position no change')
        elif diff > 0:
            _log('net buy %d, market sell' % diff)
            _order(ContextInfo, 'sell', -1, diff, 'restore_sell')
        else:
            _log('net sell %d, market buy' % abs(diff))
            _order(ContextInfo, 'buy', -1, abs(diff), 'restore_buy')

        _log('strategy finished')
