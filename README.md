# KHATA-GAMES Telegram Bot — independent rebuild

این پروژه نسخه مستقل تلگرامی است. سورس سایت فقط به‌عنوان مرجع خواندن قوانین استفاده شده و ربات به Cloudflare/D1 سایت متصل نمی‌شود و هیچ داده‌ای در سایت تغییر نمی‌دهد.

## معماری موردنظر
- هر گروه تلگرام قلعه خودش را نمایندگی می‌کند.
- هر گروه به حداکثر یک قلعه متصل می‌شود و هر قلعه فقط یک گروه دارد.
- هر حساب تلگرام حداکثر یک لرد دارد و هر قلعه حداکثر یک لرد فعال دارد.
- بازیکنان دستورات بازی را در گروه قلعه اجرا می‌کنند.
- گروه مدیریت جداگانه با `ADMIN_CHAT_ID` تعریف می‌شود.
- گزارش تجارت و جنگ به مقصدهای جداگانه قابل تنظیم ارسال می‌شوند.
- همه گروه‌ها در یک جهان و دیتابیس PostgreSQL مشترک هستند.

## راه‌اندازی ویندوز
1. دیتابیس مستقل `khata_bot` را در PostgreSQL بسازید.
2. `scripts\setup_windows.bat` را اجرا کنید.
3. از `.env.example` یک فایل `.env` بسازید.
4. `BOT_TOKEN`، `BOT_OWNER_ID`، `ADMIN_CHAT_ID` و `DATABASE_URL` را تنظیم کنید.
5. برای ساخت هش کد مدیریت اجرا کنید: `py scripts\create_admin_hash.py` و مقدار چاپ‌شده را در `ADMIN_PASSWORD_HASH` قرار دهید.
6. ربات را با `START-BOT.bat` اجرا کنید.

## ثبت گروه قلعه
ربات را به گروه اضافه کنید و مالک اصلی در همان گروه اجرا کند:

`/registercastle Winterfell | North | Stark`

قالب: `/registercastle نام قلعه | منطقه | خاندان`

سپس مالک اصلی روی پیام بازیکن Reply می‌زند و می‌نویسد:

`set lord`

ایجاد لرد و منابع اولیه در یک تراکنش دیتابیس انجام می‌شود. مقادیر شروع منابع از مهاجرت سایت گرفته شده‌اند: 500 رعیت، 5000 سکه، 500 چوب، 500 سنگ، 500 آهن، 500 گوشت، 500 ماهی، 6000 غله، صفر اسب/شیشه اژدها/وایلدفایر/قیر و 50 انگور.

## پنل مدیریت جداگانه
`ADMIN_CHAT_ID` را روی شناسه گروه خصوصی مدیریت بگذارید. فقط مالک اصلی، در همان گروه، می‌تواند `/admin <کد>` را اجرا کند. پیام حاوی کد بلافاصله حذف می‌شود. پس از احراز هویت، `/pause`، `/resume` و `/status` فعال می‌شوند.

کد مدیریت را در فایل یا پیام گروه عمومی قرار ندهید. برای کد حداقل ۱۲ نویسه استفاده کنید. هش Argon2 در `.env` قرار می‌گیرد، نه متن خام کد.

## مقصد گزارش‌ها
- `TRADE_LOG_CHAT_ID`: گروه گزارش تجارت
- `WAR_LOG_CHAT_ID`: گروه گزارش جنگ (در مرحله پیاده‌سازی موتور جنگ فعال خواهد شد)
- `STATEMENTS_CHAT_ID`: مقصد اعلان‌ها (در مرحله تکمیل سیستم اعلان)

ربات باید در این گروه‌ها عضو و مجاز به ارسال پیام باشد.

## مرجع قوانین سایت
`bot/game/site_catalog.json` خروجی ساختاریافته از `game-rules.js` و `game-data.js` سایت آپلودشده است. جزئیات منبع و جدول تطبیق در `SITE_PARITY_AUDIT.md` آمده است.

## وضعیت فعلی — مهم
این نسخه اصلاح‌شده، مشکلات ناسازگاری مدل‌ها و Handlerهای اولیه را رفع می‌کند و پایه اتصال گروه به قلعه، انتخاب لرد، منابع اولیه مطابق سایت، معامله ساده و پنل محدود مدیر را فراهم می‌کند. **این هنوز نسخه کامل هم‌ارز سایت نیست.** تولید هفتگی، ارتقاهای تولید و کمپ، سربازگیری، تجهیزات، ناوگان، محاصره، جنگ، سناریوهای نبرد، بدهی غذا، اتحادها، اعلان‌ها و پنل کامل مدیریت هنوز باید از Worker سایت به‌صورت مرحله‌ای منتقل و با تست رگرسیون تطبیق داده شوند. برای فهرست دقیق، `SITE_PARITY_AUDIT.md` را ببینید.

تا قبل از تکمیل آن موارد فقط در گروه آزمایشی استفاده شود. خاموشی لپ‌تاپ، در این نسخه هنوز موتور کامل ساعت/رویداد زمان‌دار سایت را متوقف/ادامه نمی‌دهد؛ پیاده‌سازی pause-safe scheduler مرحله بعدی است.

## دستورهای بازی در گروه قلعه
- `/profile` و `/economy`: وضعیت لرد و منابع
- `/buildings`: سطح تولیدها و کمپ‌ها
- `/upgrade production farm`: ارتقای تولید (کلیدها از `bot/game/site_catalog.json`)
- `/upgrade camp swordsman`: ارتقای کمپ عمومی
- `/upgrade special_camp ranger`: ارتقای کمپ ویژه منطقه، در صورت وجود
- `/army`: نیروها، ادوات و ناوگان
- `/workshop upgrade`: ارتقای کارگاه
- `/equipment ladder`: ساخت ادوات
- `/port upgrade`: ارتقای اسکله در قلعه‌های بندری
- `/trade` و `/offers`: تجارت پایه منابع

توجه: در منطق سایتِ موجود، سربازگیری مستقیم وجود ندارد؛ کمپ‌ها نیرو را در تسویه هفتگی تولید می‌کنند. جزئیات وضعیت انتقال قابلیت‌ها در `IMPLEMENTATION_STATUS_FA.md` است.


## جنگ و تجارت پیشرفته (نسخه یکپارچه‌سازی)

دستورات تازه گروه قلعه:
- `/march CastleName land 60 army:swordsman=100,archer=20;equipment:ladder=2`
- `/march CastleName sea 90 army:swordsman=100;fleet:transport=1,warship=1`
- `/arrivals` و سپس `/warcommand ID attack|siege|deploy`
- `/scenario ID متن سناریو`
- `/garrisons` و `/marchgarrison sourceCastleId target land|sea minutes army:swordsman=10`
- `/alliances`، `/alliance ID accept|reject`، `/transfers`، `/transfer ID accept|reject`
- `/cancelmarch ID`
- `/tradepack TELEGRAM_ID {"offer":{"wood":100,"grain":50},"request":{"iron":20}}`

دستورات گروه مدیریت پس از `/admin CODE`:
- `/adminwars`، `/warresolve ID attacker|defender JSON`
- `/adminscenarios`، `/reviewscenario ID نتیجه`
- `/admincastles`، `/admintrades`

برای JSON داوری جنگ، نمونه: `{"attacker":{"army":{"swordsman":10},"equipment":{"ladder":1}},"defender":{"army":{"spearman":5}}}`.

قبل از اجرای این نسخه روی دیتابیس قبلی، از دیتابیس `khata_bot` بکاپ بگیر و migration `bot/database/migrations/0002_warfare_trade_parity.sql` را در pgAdmin اجرا کن.
