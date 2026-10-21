# 🎓 Internshala Scraper

Internshala Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Internshala internship and job data for free.

## ✨ What Can I Get?

- 🎓 **7,000+ live internships** — stipend & stipend breakup, duration, skills, who can apply, perks, openings & applicant counts
- 💼 **6,500+ live jobs & fresher jobs** — annual CTC, experience, skills, openings, applicant counts & apply-by dates
- 🔍 **Every Internshala filter across 163 categories & 900+ cities** — work from home, part time, stipend or salary floor, duration, start date & job offer
- 🏢 **Full employer profiles** — industry, size, hiring history, candidates hired, salaries paid per role & perks

## 🎥 Example: A Full Internshala Internship

```json
{
  "id": 3281884,
  "title": "Software Development",
  "link": "https://internshala.com/internship/detail/part-time-software-development-internship-in-bangalore-at-salesforce1789133363",
  "company": {
    "name": "Salesforce",
    "website": "https://salesforce.com",
    "about": "Salesforce, Inc. is an American enterprise software company headquartered in San Francisco, California."
  },
  "locations": ["Bangalore"],
  "is_part_time": true,
  "category": "Software Development",
  "duration": { "label": "6 Months", "months": 6 },
  "stipend": { "label": "₹ 1,00,000 - 1,50,000 /month", "min": 100000, "max": 150000, "currency": "INR", "period": "monthly", "is_unpaid": false },
  "apply_by": { "label": "1 Nov' 26", "date": "2026-11-01" },
  "applicants": 1000,
  "openings": 10,
  "skills": ["Python", "React"],
  "perks": ["Certificate", "Letter of recommendation"],
  "who_can_apply": ["are available for duration of 6 months"],
  "description": "As a Software Development intern at Salesforce, you will have the opportunity to work with cutting-edge technologies such as Java, MySQL, HTML, CSS, JavaScript, Python, .NET, Node.js, C/C++ Programming, and React."
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Internshala Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/internshala-scraper
cd internshala-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/internships/details?internship=https://internshala.com/internship/detail/part-time-software-development-internship-in-bangalore-at-salesforce1789133363"
```

```json
{
  "id": 3281884,
  "title": "Software Development",
  "company": { "name": "Salesforce", "website": "https://salesforce.com", "hiring_since": "2026-08" },
  "locations": ["Bangalore"],
  "work_mode": "in_office",
  "is_part_time": true,
  "duration": { "label": "6 Months", "months": 6 },
  "stipend": { "label": "₹ 1,00,000 - 1,50,000 /month", "min": 100000, "max": 150000, "currency": "INR", "period": "monthly", "is_unpaid": false },
  "apply_by": { "label": "1 Nov' 26", "date": "2026-11-01" },
  "applicants": 1000,
  "openings": 10,
  "skills": [".NET", "C++ Programming", "CSS", "HTML", "Java", "JavaScript", "MySQL", "Node.js", "Python", "React"],
  "perks": ["Certificate", "Letter of recommendation", "Free snacks & beverages"]
}
```

All 9 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

9 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Internship Details | `/internships/details` | The full internship: stipend breakup, skills, perks, openings, applicants |
| Job Details | `/jobs/details` | The full job: annual CTC, experience, skills, openings, applicants |
| Company Details | `/companies/details` | Employer profile, salaries paid per role, perks and open listings |
| Autocomplete | `/autocomplete` | Category and city suggestions with their filter slugs |
| Search Internships | `/internships/search` | 40–60 internships per page with every Internshala filter |
| Search Jobs | `/jobs/search` | 40–60 jobs per page; salary, experience and fresher filters |
| Company Openings | `/companies/openings` | A company's open internships or jobs, page by page |
| Categories | `/categories` | All 163 internship or 157 job categories with slugs |
| Locations | `/locations` | 600+ cities with internships or jobs, with slugs |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-internshala-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-internshala-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-internshala-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/internships/search",
    params={"category": "Software Development", "location": "Bangalore"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Internshala Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Internshala%20Scraper%20API.)

[![Ask Us by Email about Internshala Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Internshala%20Scraper%20API&body=I%20need%20help%20using%20the%20Internshala%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**JobStreet Scraper**](https://github.com/omkarcloud/jobstreet-scraper) — JobStreet & JobsDB jobs, salaries, companies & reviews across 6 Asian markets
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/internshala-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/internshala-scraper)
