select
    a.user_id,
    sum(a.pay_amount) as total_pay_amount
from dwd_user_order_detail a
join dim_city b
    on a.city_id = b.city_id
group by a.user_id;
