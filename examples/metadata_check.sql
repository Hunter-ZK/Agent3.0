insert overwrite table dws_user_trade_summary
select
    user_id,
    pay_amt
from dwd_user_order_detail
where dt = '${bizdate}';
