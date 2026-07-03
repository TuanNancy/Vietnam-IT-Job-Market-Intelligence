# Vietnam IT Job Market Intelligence: từ crawl dữ liệu tuyển dụng đến phân tích bằng pandas

## Mục tiêu của project

Khi nhìn vào thị trường việc làm IT, tôi không muốn chỉ dựa vào cảm giác như “Python đang hot”, “AI đang tăng”, hay “công ty nào cũng cần Data Engineer”. Tôi muốn tự xây một pipeline nhỏ để thu thập dữ liệu tuyển dụng công khai, chuẩn hóa lại thành dataset có thể phân tích, rồi dùng pandas để kiểm tra dữ liệu thực sự đang nói gì.

Tôi gọi project này là một **data pipeline prototype** cho thị trường việc làm IT tại Việt Nam. Nó chưa phải một production system hoàn chỉnh, nhưng được thiết kế theo hướng có thể phát triển tiếp: crawler có giới hạn rõ ràng, raw data được lưu lại để tái xử lý, parser tách riêng khỏi crawler, và notebook pandas được dùng để kiểm tra chất lượng dữ liệu trước khi phân tích sâu hơn.

Project hiện tập trung vào các trang tuyển dụng IT công khai:

- `ITviec`
- `TopDev`
- `TopCV`

Bài viết này là bản ghi lại quá trình xây dựng ban đầu. Sau mỗi bước tiếp theo như làm sạch dữ liệu, chuẩn hóa kỹ năng, phân tích lương, hoặc tạo báo cáo xu hướng, tôi sẽ cập nhật thêm vào blog này.

## Tôi muốn trả lời câu hỏi gì?

Mục tiêu dài hạn của project là biến các job posting rời rạc thành một dataset có thể dùng để phân tích thị trường. Một vài câu hỏi tôi muốn trả lời:

- Kỹ năng nào xuất hiện nhiều nhất trong các tin tuyển dụng IT?
- Nguồn nào có dữ liệu lương tốt hơn?
- Dữ liệu title, company, location, skills, experience, salary có đầy đủ không?
- Các vị trí junior, middle, senior, lead đang phân bố như thế nào?
- Remote, hybrid, onsite xuất hiện ra sao trong dữ liệu tuyển dụng?
- Trước khi phân tích, dữ liệu có lỗi gì cần làm sạch?

Điểm quan trọng là tôi không bắt đầu bằng dashboard đẹp. Tôi bắt đầu bằng câu hỏi: dữ liệu có đủ tin cậy để phân tích chưa?

## Pipeline hiện tại

Pipeline hiện tại đi theo flow đơn giản:

```text
Public job pages
-> crawler
-> raw JSONL
-> parser
-> clean JSONL/CSV
-> pandas EDA notebook
-> reports / future analysis
```

Ở bước crawl, tôi lấy dữ liệu từ các job detail page công khai. Raw record được lưu dưới dạng JSONL, bao gồm HTML, JSON-LD nếu có, visible text, HTTP status, fetcher đã dùng và thời điểm crawl. Việc lưu raw data giúp tôi có thể cải thiện parser sau này mà không phải crawl lại quá nhiều lần.

Sau đó parser đọc raw JSONL và sinh ra clean JSONL/CSV với schema chung. Các field chính gồm `source`, `url`, `job_id`, `title`, `company`, `location`, `salary_raw`, `salary_min`, `salary_max`, `salary_currency`, `skills`, `experience_raw`, `experience_min`, `experience_max`, `description`, `scraped_at`, `parse_status`, `posted_at`, `location_cities`, `seniority`, `work_mode`, `employment_type`, và `salary_period`.

Notebook pandas sau đó đọc các clean CSV này để kiểm tra schema, dtype, missing value, duplicate URL, salary coverage và skill demand ban đầu.

## Vì sao dùng Scrapling?

Trong project này, `Scrapling` được dùng như fetcher ưu tiên đầu tiên. Nó cho một interface Python gọn để lấy nội dung trang, sau đó pipeline fallback về `urllib` nếu Scrapling không khả dụng hoặc không fetch được.

Tôi không dùng Scrapling như một cách để vượt captcha, Cloudflare, login wall hay anti-bot system. Vai trò của nó ở đây là giúp quá trình fetch HTML đơn giản hơn, còn crawler vẫn giữ các giới hạn an toàn: chạy tuần tự, có delay, có limit, và dừng hoặc bỏ qua khi gặp dấu hiệu bị chặn.

## Responsible crawling

Vì dữ liệu đến từ các website tuyển dụng thật, tôi đặt một số nguyên tắc ngay từ đầu:

- Tôn trọng `robots.txt`.
- Crawl tuần tự, không chạy concurrency nhanh.
- Dùng delay và limit cho mỗi lần crawl.
- Không bypass captcha, Cloudflare, login flow hoặc anti-bot system.
- Không crawl LinkedIn hoặc Google Jobs trực tiếp.
- Không scrape thông tin liên hệ cá nhân của recruiter.
- Lưu raw HTML để có thể cải thiện parser mà không cần request lại nhiều lần.

Với tôi, phần này quan trọng không kém code. Một crawler tốt không chỉ là crawler lấy được dữ liệu, mà còn phải có boundary rõ ràng.

## Tách crawler và parser

Một quyết định thiết kế quan trọng là không để crawler làm quá nhiều việc. Crawler chỉ nên lấy và lưu raw data. Parser mới là nơi chịu trách nhiệm trích xuất và chuẩn hóa field.

Cách tách này có vài lợi ích:

- Khi parser sai, tôi có thể sửa parser rồi chạy lại trên raw JSONL.
- Khi muốn thêm field mới, tôi không nhất thiết phải crawl lại ngay.
- Raw data giữ được context để debug các trường hợp khó.
- Clean output có schema thống nhất giữa nhiều nguồn.

Đây cũng là điểm tôi muốn thể hiện với nhà tuyển dụng: tôi không chỉ viết script scrape nhanh, mà đang xây một pipeline có thể kiểm tra, tái xử lý và mở rộng.

## Pandas EDA đã làm gì?

Sau khi có clean CSV, tôi tạo notebook `notebooks/01_data_inventory_eda.ipynb` để đọc và khám phá dữ liệu bằng pandas.

Các bước đã làm trong notebook:

- Load tất cả file `*_clean.csv` trong `data/processed`.
- Giữ lại `_input_file` để biết mỗi row đến từ run nào.
- Convert các cột numeric như salary và experience bằng `pd.to_numeric()`.
- Parse các cột date như `scraped_at`, `posted_at`, `valid_through` bằng `pd.to_datetime()`.
- Kiểm tra schema và dtype giữa các file.
- Tính fill-rate cho title, company, location, salary, skills, experience, description.
- Audit duplicate URL giữa các lần crawl/sample/test run.
- Tạo deduped view bằng cách giữ row có nhiều thông tin hơn.
- Tách salary numeric khỏi salary label như `You'll love it`, `Login to view salary`, `Thoả thuận`.
- Explode skills để xem demand theo kỹ năng.

Đây là bước rất quan trọng vì dữ liệu web thường không sạch ngay từ đầu. Nếu bỏ qua EDA và đi thẳng vào biểu đồ, kết quả rất dễ sai.

## Snapshot hiện tại trong repo

Ở snapshot hiện tại, notebook đọc được:

- 8 clean CSV files.
- 1,662 rows tổng cộng.
- 1,433 unique URLs.
- 421 rows nằm trong các nhóm duplicate URL.
- 1,433 rows sau khi dedupe theo URL.
- Tất cả rows hiện có `parse_status == "ok"`.

Coverage sau khi dedupe theo source:

| Source | Rows | Numeric salary rate | Skills fill rate | Experience fill rate |
| --- | ---: | ---: | ---: | ---: |
| ITviec | 750 | 27.6% | 100% | 87.73% |
| TopCV | 583 | 52.32% | 77.87% | 84.91% |
| TopDev | 100 | 0% | 100% | 83% |

Một vài diễn giải ban đầu:

- `TopCV` hiện có tỷ lệ salary numeric cao hơn `ITviec` trong snapshot này.
- `TopDev` có numeric salary rate 0% vì dữ liệu salary đang là `Login to view salary`. Đây là behavior của source, không nên xem ngay là lỗi parser.
- `ITviec` có nhiều salary label dạng `You'll love it`, nên cần tách hidden/marketing salary label khỏi salary numeric.
- Duplicate URL xuất hiện vì notebook đang load nhiều run khác nhau, bao gồm sample, test, full run và salary-focused run.
- Salary audit hiện flag 8 rows suspicious numeric salary, cần kiểm tra trước khi dùng cho phân tích lương.

Những con số này không phải kết luận cuối cùng về thị trường. Đây là snapshot hiện tại để kiểm tra data quality và sẽ thay đổi khi tôi crawl thêm, làm sạch thêm và chuẩn hóa logic phân tích.

## Bài học từ dữ liệu ban đầu

Điểm thú vị nhất ở giai đoạn này là mỗi nguồn có “tính cách dữ liệu” khác nhau.

`TopCV` có nhiều dòng lương numeric hơn, nhưng skills fill rate thấp hơn `ITviec` và `TopDev`. `TopDev` có skills và experience tương đối đầy đủ, nhưng salary numeric lại không dùng được vì bị ẩn sau login. `ITviec` có skills đầy đủ, nhưng salary thường là label không numeric.

Điều này nhắc tôi rằng phân tích dữ liệu tuyển dụng không thể chỉ concat tất cả nguồn rồi groupby. Cần hiểu field nào dùng được cho bài toán nào:

- Demand theo skills có thể dùng cả ba nguồn.
- Salary analysis nên chỉ dùng rows có numeric salary hợp lệ.
- Source quality report cần phân biệt “missing do parser” và “hidden do website behavior”.
- Duplicate handling phải dựa trên URL và chất lượng row, không chỉ drop bừa row đầu tiên.

## Pandas không chỉ để tính toán, mà để hiểu dữ liệu

Ở giai đoạn này, pandas giúp tôi học và thực hành nhiều thao tác data cleaning cơ bản nhưng rất thực tế:

- `read_csv()` để đọc nhiều file clean CSV.
- `concat()` để gom nhiều run thành một DataFrame.
- `to_numeric()` để chuẩn hóa salary và experience.
- `to_datetime()` để parse timestamp.
- `groupby().agg()` để tính coverage theo source và file.
- `duplicated()` và `drop_duplicates()` để audit duplicate URL.
- `isna()`, `notna()`, `fillna()` để kiểm tra missingness.
- `str.strip()`, `str.contains()` để xử lý text field.
- `explode()` để biến skills list thành bảng long format.

Tôi đang dùng pandas không chỉ để “ra số”, mà để trả lời câu hỏi: dữ liệu này có đáng tin không, còn thiếu gì, và bước cleaning tiếp theo nên ưu tiên ở đâu?

## Project này thể hiện điều gì với nhà tuyển dụng?

Nếu dùng project này trong một buổi phỏng vấn, tôi muốn nó thể hiện các năng lực sau:

- Biết thiết kế pipeline theo từng tầng: crawl, raw storage, parse, clean data, EDA, report.
- Biết tách trách nhiệm giữa crawler và parser.
- Biết giữ raw data để tái xử lý, thay vì chỉ lấy output cuối cùng.
- Biết nhìn dữ liệu bằng fill-rate, duplicate audit, dtype check và suspicious-row check.
- Biết nói rõ giới hạn của dữ liệu, ví dụ salary bị hidden ở một số nguồn.
- Biết crawl có trách nhiệm, không cố vượt login/captcha/anti-bot.
- Biết dùng pandas để kiểm tra data quality trước khi phân tích thị trường.

Nói ngắn gọn, project này không chỉ là “scrape job postings”. Nó là bài tập thực tế về cách biến dữ liệu web lộn xộn thành một dataset có thể audit và phân tích.

## Next steps

Các bước tiếp theo tôi dự định cập nhật vào blog này:

- Thêm notebook-only cleaning views bằng pandas.
- Chọn canonical row cho mỗi URL bằng quality score rõ ràng.
- Classify salary thành numeric, negotiable, hidden, missing, suspicious.
- Normalize skills để gom các biến thể như `Javascript`, `JavaScript`, `Typescript`, `TypeScript`.
- Tạo `skills_long` để phân tích demand theo kỹ năng.
- Chuẩn hóa location, city và work mode cho phân tích remote/hybrid/onsite.
- Tạo issue log để biết mỗi row đang có vấn đề gì.
- Regenerate trend reports khi cleaning rules ổn định.
- Về lâu dài, có thể harden project bằng scheduler, storage layer, CI checks, monitoring và dashboard.

## Kết luận

Project này bắt đầu từ một câu hỏi đơn giản: thị trường IT Việt Nam đang cần gì? Nhưng để trả lời nghiêm túc, tôi cần làm nhiều việc trước khi phân tích: crawl có trách nhiệm, lưu raw data, parse thành schema chung, kiểm tra dữ liệu bằng pandas và làm sạch từng vấn đề một.

Đây mới là data pipeline prototype, nhưng nó đang đi theo hướng tôi muốn: minh bạch, kiểm tra được, tái xử lý được và có thể mở rộng thành một hệ thống market intelligence hoàn chỉnh hơn.
