# frozen_string_literal: true

require "cgi"
require "uri"

# Pay-link identity from books (QBO InvoiceLink, Stripe, PayPal, etc.).
# Generic last-path words are not identifiers. Mail matches the stored URL or a
# unique query/path token from it — owner send, CPA forward, or Gmail-wrapped href.
module Invoices::PayLink
  GENERIC_SEGMENTS = %w[
    invoice invoices pay payment payments portal app index view checkout
    link connect intuit qbo xero stripe paypal billing cart www http https
    html php asp aspx
  ].freeze

  UNIQUE_QUERY_KEYS = %w[
    txnid jobid invoiceid id token guid pid paymentid invoicenumber
  ].freeze

  STORED_MAX = 255
  MIN_NEEDLE = 6

  module_function

  def stored_token(url)
    raw = url.to_s.strip
    return if raw.blank?

    if uri?(raw)
      return raw if raw.length <= STORED_MAX

      return unique_parts(raw).max_by(&:length)
    end

    usable_needle?(raw) ? raw[0, STORED_MAX] : nil
  end

  def match?(stored, haystack)
    text = haystack.to_s.downcase
    return false if text.blank?

    match_needles(stored).any? { |needle| text.include?(needle.downcase) }
  end

  def match_needles(stored)
    raw = stored.to_s.strip
    return [] if raw.blank?

    needles = []
    needles << raw if usable_needle?(raw) || uri?(raw)
    needles.concat(unique_parts(raw))
    needles.map { |part| part.to_s.strip }.reject(&:blank?).uniq.select do |part|
      usable_needle?(part) || uri?(part)
    end
  end

  def search_terms(stored)
    raw = stored.to_s.strip
    return [] if raw.blank?

    terms = unique_parts(raw)
    return terms if terms.any?
    return [ raw ] if usable_needle?(raw) && !uri?(raw)

    uri = parse_uri(raw)
    return [] if uri.blank?

    terms << uri.query if uri.query.to_s.length >= MIN_NEEDLE
    last = last_path(uri)
    terms << last if numbered_segment?(last)
    terms.compact.uniq
  end

  def urls_in(text)
    found = text.to_s.scan(%r{https?://[^\s"'<>]+}i)
    found.flat_map do |url|
      nested = []
      uri = parse_uri(url)
      if uri&.query.present?
        CGI.parse(uri.query).each_value do |values|
          nested.concat(values.select { |value| value.to_s.match?(/\Ahttps?:\/\//i) })
        end
      end
      [ url, CGI.unescape(url) ] + nested
    rescue ArgumentError
      [ url ]
    end.uniq.join(" ")
  end

  def unique_parts(value)
    uri = parse_uri(value)
    parts = []
    if uri
      query_values(uri).each { |item| parts << item if distinctive?(item) }
      last = last_path(uri)
      parts << last if distinctive?(last)
    elsif distinctive?(value)
      parts << value
    end
    parts.uniq
  end

  def distinctive?(value)
    part = value.to_s.strip
    return false unless usable_needle?(part)
    return false if generic_segment?(part)
    return true if guid?(part)

    part.match?(/[0-9]/) && part.length >= 8
  end

  def usable_needle?(value)
    part = value.to_s.strip
    part.length >= MIN_NEEDLE && !generic_segment?(part)
  end

  def generic_segment?(value)
    GENERIC_SEGMENTS.include?(value.to_s.strip.downcase)
  end

  def numbered_segment?(value)
    part = value.to_s.strip
    part.present? && !generic_segment?(part) && part.match?(/[0-9]/) && part.length >= MIN_NEEDLE
  end

  def guid?(value)
    part = value.to_s.strip
    part.match?(/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i) ||
      part.match?(/\A[0-9a-f]{16,}\z/i)
  end

  def uri?(value)
    parse_uri(value).present?
  end

  def parse_uri(value)
    raw = value.to_s.strip
    return unless raw.match?(/\Ahttps?:\/\//i)

    uri = URI.parse(raw)
    uri if uri.host.present?
  rescue URI::InvalidURIError
    nil
  end

  def last_path(uri)
    uri.path.to_s.split("/").reject(&:blank?).last
  end

  def query_values(uri)
    CGI.parse(uri.query.to_s).flat_map do |key, values|
      normalized = key.to_s.downcase.gsub(/[\-_]/, "")
      UNIQUE_QUERY_KEYS.include?(normalized) ? values : []
    end
  end
end
