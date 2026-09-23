# frozen_string_literal: true

# Calendar date from a human reply. No invented dates. No LLM.
module Email::ParseWaitDate
  MONTHS = Date::MONTHNAMES.compact.each_with_index.to_h { |name, index| [ name.downcase, index ] }
    .merge(Date::ABBR_MONTHNAMES.compact.each_with_index.to_h { |name, index| [ name.downcase, index ] })
  WEEKDAYS = Date::DAYNAMES.each_with_index.to_h { |name, index| [ name.downcase, index ] }
    .merge(Date::ABBR_DAYNAMES.each_with_index.to_h { |name, index| [ name.downcase, index ] })

  module_function

  def extract(text, as_of:)
    source = text.to_s
    return if source.blank? || as_of.blank?

    iso = source[/\b(\d{4}-\d{2}-\d{2})\b/, 1]
    parsed = parse_iso(iso) || parse_named_month(source, as_of) || parse_weekday(source, as_of)
    return if parsed.blank? || parsed < as_of.to_date

    quote = quote_for(source, parsed, iso)
    { date: parsed, quote: quote }
  end

  def parse_iso(value)
    return if value.blank?

    Date.iso8601(value)
  rescue Date::Error
    nil
  end

  def parse_named_month(source, as_of)
    match = source.match(/\b(\d{1,2})\s+(#{MONTHS.keys.join("|")})(?:\s+(\d{4}))?\b/i) ||
      source.match(/\b(#{MONTHS.keys.join("|")})\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b/i)
    return if match.blank?

    month_token, day_token, year_token = named_parts(match)
    month = MONTHS[month_token.downcase]
    day = day_token.to_i
    year = year_token.present? ? year_token.to_i : as_of.to_date.year
    date = Date.new(year, month, day)
    date += 1.year if year_token.blank? && date < as_of.to_date
    date
  rescue Date::Error, ArgumentError
    nil
  end

  def named_parts(match)
    if match[1].to_s.match?(/\A\d+\z/)
      [ match[2], match[1], match[3] ]
    else
      [ match[1], match[2], match[3] ]
    end
  end

  def parse_weekday(source, as_of)
    match = source.match(/\b(?:this|next)?\s*(#{WEEKDAYS.keys.join("|")})\b/i)
    return if match.blank?

    target = WEEKDAYS[match[1].downcase]
    start = as_of.to_date
    delta = (target - start.wday) % 7
    delta = 7 if delta.zero?
    start + delta
  end

  def quote_for(source, date, iso)
    return iso if iso.present?

    source.lines.map(&:strip).find { |line| line.match?(/pay|friday|monday|tuesday|wednesday|thursday|saturday|sunday|#{date.strftime("%-d")}/i) } ||
      source.to_s.strip.truncate(160)
  end
end
