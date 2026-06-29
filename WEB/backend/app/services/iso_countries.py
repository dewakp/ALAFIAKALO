"""ISO 3166 country tables (generated from pycountry) + free-text name resolver.

Used by disease surveillance to normalize sources: WHO GHO emits ISO3, our user/
report rows store free-text country names, and the frontend map keys on ISO2.
"""
import re

# ISO 3166-1 alpha-3 -> alpha-2 (WHO GHO SpatialDim is alpha-3).
ISO3_TO_ISO2 = {
    "ABW": "AW", "AFG": "AF", "AGO": "AO", "AIA": "AI", "ALA": "AX", "ALB": "AL", "AND": "AD",
    "ARE": "AE", "ARG": "AR", "ARM": "AM", "ASM": "AS", "ATA": "AQ", "ATF": "TF", "ATG": "AG",
    "AUS": "AU", "AUT": "AT", "AZE": "AZ", "BDI": "BI", "BEL": "BE", "BEN": "BJ", "BES": "BQ",
    "BFA": "BF", "BGD": "BD", "BGR": "BG", "BHR": "BH", "BHS": "BS", "BIH": "BA", "BLM": "BL",
    "BLR": "BY", "BLZ": "BZ", "BMU": "BM", "BOL": "BO", "BRA": "BR", "BRB": "BB", "BRN": "BN",
    "BTN": "BT", "BVT": "BV", "BWA": "BW", "CAF": "CF", "CAN": "CA", "CCK": "CC", "CHE": "CH",
    "CHL": "CL", "CHN": "CN", "CIV": "CI", "CMR": "CM", "COD": "CD", "COG": "CG", "COK": "CK",
    "COL": "CO", "COM": "KM", "CPV": "CV", "CRI": "CR", "CUB": "CU", "CUW": "CW", "CXR": "CX",
    "CYM": "KY", "CYP": "CY", "CZE": "CZ", "DEU": "DE", "DJI": "DJ", "DMA": "DM", "DNK": "DK",
    "DOM": "DO", "DZA": "DZ", "ECU": "EC", "EGY": "EG", "ERI": "ER", "ESH": "EH", "ESP": "ES",
    "EST": "EE", "ETH": "ET", "FIN": "FI", "FJI": "FJ", "FLK": "FK", "FRA": "FR", "FRO": "FO",
    "FSM": "FM", "GAB": "GA", "GBR": "GB", "GEO": "GE", "GGY": "GG", "GHA": "GH", "GIB": "GI",
    "GIN": "GN", "GLP": "GP", "GMB": "GM", "GNB": "GW", "GNQ": "GQ", "GRC": "GR", "GRD": "GD",
    "GRL": "GL", "GTM": "GT", "GUF": "GF", "GUM": "GU", "GUY": "GY", "HKG": "HK", "HMD": "HM",
    "HND": "HN", "HRV": "HR", "HTI": "HT", "HUN": "HU", "IDN": "ID", "IMN": "IM", "IND": "IN",
    "IOT": "IO", "IRL": "IE", "IRN": "IR", "IRQ": "IQ", "ISL": "IS", "ISR": "IL", "ITA": "IT",
    "JAM": "JM", "JEY": "JE", "JOR": "JO", "JPN": "JP", "KAZ": "KZ", "KEN": "KE", "KGZ": "KG",
    "KHM": "KH", "KIR": "KI", "KNA": "KN", "KOR": "KR", "KWT": "KW", "LAO": "LA", "LBN": "LB",
    "LBR": "LR", "LBY": "LY", "LCA": "LC", "LIE": "LI", "LKA": "LK", "LSO": "LS", "LTU": "LT",
    "LUX": "LU", "LVA": "LV", "MAC": "MO", "MAF": "MF", "MAR": "MA", "MCO": "MC", "MDA": "MD",
    "MDG": "MG", "MDV": "MV", "MEX": "MX", "MHL": "MH", "MKD": "MK", "MLI": "ML", "MLT": "MT",
    "MMR": "MM", "MNE": "ME", "MNG": "MN", "MNP": "MP", "MOZ": "MZ", "MRT": "MR", "MSR": "MS",
    "MTQ": "MQ", "MUS": "MU", "MWI": "MW", "MYS": "MY", "MYT": "YT", "NAM": "NA", "NCL": "NC",
    "NER": "NE", "NFK": "NF", "NGA": "NG", "NIC": "NI", "NIU": "NU", "NLD": "NL", "NOR": "NO",
    "NPL": "NP", "NRU": "NR", "NZL": "NZ", "OMN": "OM", "PAK": "PK", "PAN": "PA", "PCN": "PN",
    "PER": "PE", "PHL": "PH", "PLW": "PW", "PNG": "PG", "POL": "PL", "PRI": "PR", "PRK": "KP",
    "PRT": "PT", "PRY": "PY", "PSE": "PS", "PYF": "PF", "QAT": "QA", "REU": "RE", "ROU": "RO",
    "RUS": "RU", "RWA": "RW", "SAU": "SA", "SDN": "SD", "SEN": "SN", "SGP": "SG", "SGS": "GS",
    "SHN": "SH", "SJM": "SJ", "SLB": "SB", "SLE": "SL", "SLV": "SV", "SMR": "SM", "SOM": "SO",
    "SPM": "PM", "SRB": "RS", "SSD": "SS", "STP": "ST", "SUR": "SR", "SVK": "SK", "SVN": "SI",
    "SWE": "SE", "SWZ": "SZ", "SXM": "SX", "SYC": "SC", "SYR": "SY", "TCA": "TC", "TCD": "TD",
    "TGO": "TG", "THA": "TH", "TJK": "TJ", "TKL": "TK", "TKM": "TM", "TLS": "TL", "TON": "TO",
    "TTO": "TT", "TUN": "TN", "TUR": "TR", "TUV": "TV", "TWN": "TW", "TZA": "TZ", "UGA": "UG",
    "UKR": "UA", "UMI": "UM", "URY": "UY", "USA": "US", "UZB": "UZ", "VAT": "VA", "VCT": "VC",
    "VEN": "VE", "VGB": "VG", "VIR": "VI", "VNM": "VN", "VUT": "VU", "WLF": "WF", "WSM": "WS",
    "YEM": "YE", "ZAF": "ZA", "ZMB": "ZM", "ZWE": "ZW",
}

# ISO 3166-1 alpha-3 -> common country name.
ISO3_TO_NAME = {
    "ABW": "Aruba", "AFG": "Afghanistan", "AGO": "Angola", "AIA": "Anguilla",
    "ALA": "Åland Islands", "ALB": "Albania", "AND": "Andorra", "ARE": "United Arab Emirates",
    "ARG": "Argentina", "ARM": "Armenia", "ASM": "American Samoa", "ATA": "Antarctica",
    "ATF": "French Southern Territories", "ATG": "Antigua and Barbuda", "AUS": "Australia",
    "AUT": "Austria", "AZE": "Azerbaijan", "BDI": "Burundi", "BEL": "Belgium", "BEN": "Benin",
    "BES": "Bonaire, Sint Eustatius and Saba", "BFA": "Burkina Faso", "BGD": "Bangladesh",
    "BGR": "Bulgaria", "BHR": "Bahrain", "BHS": "Bahamas", "BIH": "Bosnia and Herzegovina",
    "BLM": "Saint Barthélemy", "BLR": "Belarus", "BLZ": "Belize", "BMU": "Bermuda",
    "BOL": "Bolivia", "BRA": "Brazil", "BRB": "Barbados", "BRN": "Brunei Darussalam",
    "BTN": "Bhutan", "BVT": "Bouvet Island", "BWA": "Botswana",
    "CAF": "Central African Republic", "CAN": "Canada", "CCK": "Cocos (Keeling) Islands",
    "CHE": "Switzerland", "CHL": "Chile", "CHN": "China", "CIV": "Côte d'Ivoire",
    "CMR": "Cameroon", "COD": "Congo, The Democratic Republic of the", "COG": "Congo",
    "COK": "Cook Islands", "COL": "Colombia", "COM": "Comoros", "CPV": "Cabo Verde",
    "CRI": "Costa Rica", "CUB": "Cuba", "CUW": "Curaçao", "CXR": "Christmas Island",
    "CYM": "Cayman Islands", "CYP": "Cyprus", "CZE": "Czechia", "DEU": "Germany",
    "DJI": "Djibouti", "DMA": "Dominica", "DNK": "Denmark", "DOM": "Dominican Republic",
    "DZA": "Algeria", "ECU": "Ecuador", "EGY": "Egypt", "ERI": "Eritrea",
    "ESH": "Western Sahara", "ESP": "Spain", "EST": "Estonia", "ETH": "Ethiopia",
    "FIN": "Finland", "FJI": "Fiji", "FLK": "Falkland Islands (Malvinas)", "FRA": "France",
    "FRO": "Faroe Islands", "FSM": "Micronesia, Federated States of", "GAB": "Gabon",
    "GBR": "United Kingdom", "GEO": "Georgia", "GGY": "Guernsey", "GHA": "Ghana",
    "GIB": "Gibraltar", "GIN": "Guinea", "GLP": "Guadeloupe", "GMB": "Gambia",
    "GNB": "Guinea-Bissau", "GNQ": "Equatorial Guinea", "GRC": "Greece", "GRD": "Grenada",
    "GRL": "Greenland", "GTM": "Guatemala", "GUF": "French Guiana", "GUM": "Guam",
    "GUY": "Guyana", "HKG": "Hong Kong", "HMD": "Heard Island and McDonald Islands",
    "HND": "Honduras", "HRV": "Croatia", "HTI": "Haiti", "HUN": "Hungary", "IDN": "Indonesia",
    "IMN": "Isle of Man", "IND": "India", "IOT": "British Indian Ocean Territory",
    "IRL": "Ireland", "IRN": "Iran", "IRQ": "Iraq", "ISL": "Iceland", "ISR": "Israel",
    "ITA": "Italy", "JAM": "Jamaica", "JEY": "Jersey", "JOR": "Jordan", "JPN": "Japan",
    "KAZ": "Kazakhstan", "KEN": "Kenya", "KGZ": "Kyrgyzstan", "KHM": "Cambodia",
    "KIR": "Kiribati", "KNA": "Saint Kitts and Nevis", "KOR": "South Korea", "KWT": "Kuwait",
    "LAO": "Laos", "LBN": "Lebanon", "LBR": "Liberia", "LBY": "Libya", "LCA": "Saint Lucia",
    "LIE": "Liechtenstein", "LKA": "Sri Lanka", "LSO": "Lesotho", "LTU": "Lithuania",
    "LUX": "Luxembourg", "LVA": "Latvia", "MAC": "Macao", "MAF": "Saint Martin (French part)",
    "MAR": "Morocco", "MCO": "Monaco", "MDA": "Moldova", "MDG": "Madagascar",
    "MDV": "Maldives", "MEX": "Mexico", "MHL": "Marshall Islands", "MKD": "North Macedonia",
    "MLI": "Mali", "MLT": "Malta", "MMR": "Myanmar", "MNE": "Montenegro", "MNG": "Mongolia",
    "MNP": "Northern Mariana Islands", "MOZ": "Mozambique", "MRT": "Mauritania",
    "MSR": "Montserrat", "MTQ": "Martinique", "MUS": "Mauritius", "MWI": "Malawi",
    "MYS": "Malaysia", "MYT": "Mayotte", "NAM": "Namibia", "NCL": "New Caledonia",
    "NER": "Niger", "NFK": "Norfolk Island", "NGA": "Nigeria", "NIC": "Nicaragua",
    "NIU": "Niue", "NLD": "Netherlands", "NOR": "Norway", "NPL": "Nepal", "NRU": "Nauru",
    "NZL": "New Zealand", "OMN": "Oman", "PAK": "Pakistan", "PAN": "Panama", "PCN": "Pitcairn",
    "PER": "Peru", "PHL": "Philippines", "PLW": "Palau", "PNG": "Papua New Guinea",
    "POL": "Poland", "PRI": "Puerto Rico", "PRK": "North Korea", "PRT": "Portugal",
    "PRY": "Paraguay", "PSE": "Palestine, State of", "PYF": "French Polynesia", "QAT": "Qatar",
    "REU": "Réunion", "ROU": "Romania", "RUS": "Russian Federation", "RWA": "Rwanda",
    "SAU": "Saudi Arabia", "SDN": "Sudan", "SEN": "Senegal", "SGP": "Singapore",
    "SGS": "South Georgia and the South Sandwich Islands",
    "SHN": "Saint Helena, Ascension and Tristan da Cunha", "SJM": "Svalbard and Jan Mayen",
    "SLB": "Solomon Islands", "SLE": "Sierra Leone", "SLV": "El Salvador", "SMR": "San Marino",
    "SOM": "Somalia", "SPM": "Saint Pierre and Miquelon", "SRB": "Serbia",
    "SSD": "South Sudan", "STP": "Sao Tome and Principe", "SUR": "Suriname", "SVK": "Slovakia",
    "SVN": "Slovenia", "SWE": "Sweden", "SWZ": "Eswatini", "SXM": "Sint Maarten (Dutch part)",
    "SYC": "Seychelles", "SYR": "Syria", "TCA": "Turks and Caicos Islands", "TCD": "Chad",
    "TGO": "Togo", "THA": "Thailand", "TJK": "Tajikistan", "TKL": "Tokelau",
    "TKM": "Turkmenistan", "TLS": "Timor-Leste", "TON": "Tonga", "TTO": "Trinidad and Tobago",
    "TUN": "Tunisia", "TUR": "Türkiye", "TUV": "Tuvalu", "TWN": "Taiwan", "TZA": "Tanzania",
    "UGA": "Uganda", "UKR": "Ukraine", "UMI": "United States Minor Outlying Islands",
    "URY": "Uruguay", "USA": "United States", "UZB": "Uzbekistan",
    "VAT": "Holy See (Vatican City State)", "VCT": "Saint Vincent and the Grenadines",
    "VEN": "Venezuela", "VGB": "Virgin Islands, British", "VIR": "Virgin Islands, U.S.",
    "VNM": "Vietnam", "VUT": "Vanuatu", "WLF": "Wallis and Futuna", "WSM": "Samoa",
    "YEM": "Yemen", "ZAF": "South Africa", "ZMB": "Zambia", "ZWE": "Zimbabwe",
}

# alpha-2 -> common country name.
ISO2_TO_NAME = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania", "AM": "Armenia",
    "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina", "AS": "American Samoa",
    "AT": "Austria", "AU": "Australia", "AW": "Aruba", "AX": "Åland Islands",
    "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados", "BD": "Bangladesh",
    "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi",
    "BJ": "Benin", "BL": "Saint Barthélemy", "BM": "Bermuda", "BN": "Brunei Darussalam",
    "BO": "Bolivia", "BQ": "Bonaire, Sint Eustatius and Saba", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize",
    "CA": "Canada", "CC": "Cocos (Keeling) Islands",
    "CD": "Congo, The Democratic Republic of the", "CF": "Central African Republic",
    "CG": "Congo", "CH": "Switzerland", "CI": "Côte d'Ivoire", "CK": "Cook Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba", "CV": "Cabo Verde", "CW": "Curaçao", "CX": "Christmas Island",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark",
    "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea", "ES": "Spain",
    "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands (Malvinas)",
    "FM": "Micronesia, Federated States of", "FO": "Faroe Islands", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia",
    "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar",
    "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala", "GU": "Guam",
    "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras", "HR": "Croatia",
    "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel",
    "IM": "Isle of Man", "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq",
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JE": "Jersey", "JM": "Jamaica",
    "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia",
    "KI": "Kiribati", "KM": "Comoros", "KN": "Saint Kitts and Nevis", "KP": "North Korea",
    "KR": "South Korea", "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MC": "Monaco", "MD": "Moldova",
    "ME": "Montenegro", "MF": "Saint Martin (French part)", "MG": "Madagascar",
    "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar",
    "MN": "Mongolia", "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius", "MV": "Maldives",
    "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia",
    "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru",
    "NU": "Niue", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn", "PR": "Puerto Rico",
    "PS": "Palestine, State of", "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RE": "Réunion", "RO": "Romania", "RS": "Serbia",
    "RU": "Russian Federation", "RW": "Rwanda", "SA": "Saudi Arabia", "SB": "Solomon Islands",
    "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "Saint Helena, Ascension and Tristan da Cunha", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino",
    "SN": "Senegal", "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan",
    "ST": "Sao Tome and Principe", "SV": "El Salvador", "SX": "Sint Maarten (Dutch part)",
    "SY": "Syria", "SZ": "Eswatini", "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga",
    "TR": "Türkiye", "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan",
    "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "United States Minor Outlying Islands", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Holy See (Vatican City State)",
    "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela",
    "VG": "Virgin Islands, British", "VI": "Virgin Islands, U.S.", "VN": "Vietnam",
    "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Common free-text aliases that don't match the canonical names above.
_ALIASES = {
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "united states of america": "US",
    "america": "US", "uk": "GB", "u.k.": "GB", "britain": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "south korea": "KR", "north korea": "KP", "russia": "RU", "iran": "IR",
    "syria": "SY", "vietnam": "VN", "laos": "LA", "moldova": "MD", "bolivia": "BO",
    "venezuela": "VE", "tanzania": "TZ", "ivory coast": "CI", "cote d'ivoire": "CI",
    "cote divoire": "CI", "drc": "CD", "dr congo": "CD", "democratic republic of congo": "CD",
    "congo": "CG", "republic of congo": "CG", "uae": "AE", "united arab emirates": "AE",
    "czech republic": "CZ", "czechia": "CZ", "swaziland": "SZ", "cape verde": "CV",
    "burma": "MM", "myanmar": "MM", "palestine": "PS", "macedonia": "MK",
    "north macedonia": "MK", "brunei": "BN", "the gambia": "GM", "gambia": "GM",
    "taiwan": "TW", "hong kong": "HK", "macau": "MO", "macao": "MO",
}

# name (lowercased) -> alpha-2, from canonical names.
_NAME_TO_ISO2 = {v.lower(): k for k, v in ISO2_TO_NAME.items()}
_NAME_TO_ISO2.update(_ALIASES)


def resolve_country(value: str | None) -> str | None:
    """Resolve a free-text country name (or ISO2/ISO3 code) to ISO 3166-1 alpha-2."""
    if not value:
        return None
    v = value.strip()
    up = v.upper()
    if len(up) == 2 and up in ISO2_TO_NAME:
        return up
    if len(up) == 3 and up in ISO3_TO_ISO2:
        return ISO3_TO_ISO2[up]
    low = re.sub(r"\s+", " ", v.lower()).strip(" .,")
    if low in _NAME_TO_ISO2:
        return _NAME_TO_ISO2[low]
    # Loose contains match for "Republic of X" style strings.
    for name, code in _NAME_TO_ISO2.items():
        if len(name) > 4 and name in low:
            return code
    return None
