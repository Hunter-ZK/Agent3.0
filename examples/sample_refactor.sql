insert overwrite dws_user_trade_summary
select
    user_id,
    sum(pay_amount) as total_pay_amount
from dwd_user_order_detail
where dt = '20260601'
group by user_id;

select * from dwd_user_order_detail;
