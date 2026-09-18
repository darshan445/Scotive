# frozen_string_literal: true

require "json"

# In-process + Redis flag for Sync Now running state. Test uses memory; Sidekiq uses Redis.
class Sync::State
  TTL_SECONDS = 15.minutes.to_i

  class << self
    def running?(organization_id)
      read(running_key(organization_id)).present?
    end

    def mark_running!(organization_id)
      write(running_key(organization_id), true)
    end

    def clear_running!(organization_id)
      delete(running_key(organization_id))
    end

    def store_counts!(organization_id, counts)
      write(counts_key(organization_id), counts)
    end

    def last_counts(organization_id)
      value = read(counts_key(organization_id))
      value.is_a?(Hash) ? value.with_indifferent_access : {}
    end

    def reset!
      @memory = {}
    end

    private

    def running_key(organization_id)
      "sync:#{organization_id}:running"
    end

    def counts_key(organization_id)
      "sync:#{organization_id}:counts"
    end

    def write(key, value)
      payload = JSON.generate(value)
      memory[key] = { payload: payload, expires_at: Time.current + TTL_SECONDS }
      redis_write(key, payload)
    end

    def read(key)
      payload = redis_read(key)
      payload ||= memory_payload(key)
      return if payload.blank?

      JSON.parse(payload)
    rescue JSON::ParserError
      payload
    end

    def delete(key)
      memory.delete(key)
      redis_delete(key)
    end

    def memory
      @memory ||= {}
    end

    def memory_payload(key)
      entry = memory[key]
      return if entry.blank?
      return memory.delete(key) && nil if entry[:expires_at] < Time.current

      entry[:payload]
    end

    def redis_write(key, payload)
      Sidekiq.redis { |redis| redis.set(key, payload, ex: TTL_SECONDS) }
    rescue StandardError
      nil
    end

    def redis_read(key)
      Sidekiq.redis { |redis| redis.get(key) }
    rescue StandardError
      nil
    end

    def redis_delete(key)
      Sidekiq.redis { |redis| redis.del(key) }
    rescue StandardError
      nil
    end
  end
end
