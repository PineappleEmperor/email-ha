[![release][release-badge]][release-url]
[![commits-since-latest][commits-badge]][commits-url]
![stars][stars-badge]
![Dynamic Regex Badge][hacs-badge]
\
![build][python-badge]
![build][hassfest-badge]
![build][hacs-valid-badge]

# Email IMAP for Home Assistant
Email HA allows you to connect to your gmail email using OAuth2, and allows for IMAP queries.

---

## Features

| What | Details |
|---|---|
| **Sensors** | Unread count · Last email subject (+ sender, date, preview as attributes) |
| **Service** | `email_imap.query_emails` — run any IMAP search and get results back as a response variable |
| **Events** | `email_imap_new_email` fired whenever the latest email changes |

---

## Prerequisites

### Gmail

1. Enable IMAP in Gmail **Settings → See all settings → Forwarding and POP/IMAP**.
2. In [Google Cloud Console](https://console.cloud.google.com/):
   - Create a project and enable the **Gmail API**.
   - Create an **OAuth 2.0 Client ID** (Web application type).
   - Add your HA instance URL + `/auth/external/callback` as an authorised redirect URI.
   - Note the **Client ID** and **Client Secret**.

---

## Installation

### HACS (recommended)

1. In HACS go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/PineappleEmperor/email-ha` with category **Integration**.
3. Install **Email HA** and restart Home Assistant.

### Manual

Copy `custom_components/email_imap/` into your HA `config/custom_components/` directory and restart.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration** and search for **Email IMAP**.
2. Select your provider, enter your email address, Client ID, and Client Secret.
3. Complete the OAuth2 browser flow.
4. Set the IMAP folder, poll count, and scan interval.

---

## Sensors

After setup, two sensors are created per account:

| Entity | State | Key attributes |
|---|---|---|
| `sensor.email_imap_<email>_unread_count` | Number of unseen messages | `folder` |
| `sensor.email_imap_<email>_last_email` | Subject of most-recent email | `sender`, `date`, `preview`, `message_id`, `uid`, `folder` |

---

## Service: `email_imap.query_emails`

Run a custom IMAP search and receive the results as a service response.

```yaml
service: email_imap.query_emails
data:
  folder: INBOX
  search_criteria: "UNSEEN FROM boss@example.com"
  max_results: 5
response_variable: result
```

`result.emails` is a list of objects with fields:
`uid`, `subject`, `sender`, `date`, `message_id`, `preview`.

### IMAP search criteria examples

| Goal | Criteria |
|---|---|
| All unread | `UNSEEN` |
| From a sender | `FROM user@example.com` |
| Subject contains | `SUBJECT "invoice"` |
| Since a date | `SINCE 01-May-2025` |
| Unread + from | `UNSEEN FROM boss@example.com` |

---


<!-- Badges -->

[commits-badge]: https://img.shields.io/github/commits-since/PineappleEmperor/email-ha/latest?style=flat-square
[downloads-badge]: https://img.shields.io/github/downloads/pineappleemperor/email-ha/total?style=flat-square
[hacs-badge]: https://img.shields.io/badge/dynamic/regex?url=https%3A%2F%2Fraw.githubusercontent.com%2Fhacs%2Fdefault%2Frefs%2Fheads%2Fmaster%2Fintegration&search=(%22PineappleEmperor%2Femail-ha%22)&replace=default&style=flat-square&label=hacs&link=https%3A%2F%2Fgithub.com%2Fhacs%2Fintegration
[hacs-valid-badge]: https://img.shields.io/github/actions/workflow/status/PineappleEmperor/email-ha/hacs_validate.yml?style=flat-square&label=hacs%20valid
[release-badge]: https://img.shields.io/github/v/release/PineappleEmperor/email-ha?style=flat-square
[stars-badge]: https://img.shields.io/github/stars/PineappleEmperor/email-ha?style=flat-square
[hassfest-badge]: https://img.shields.io/github/actions/workflow/status/PineappleEmperor/email-ha/hassfest_validate.yml?style=flat-square&label=hassfest
[python-badge]: https://img.shields.io/github/actions/workflow/status/PineappleEmperor/email-ha/python_validate.yml?style=flat-square&label=python

<!-- References -->

[commits-url]: https://github.com/PineappleEmperor/email-ha/commits/main/
[hacs-url]: https://github.com/hacs/integration
[release-url]: https://github.com/PineappleEmperor/email-ha/releases
