# frozen_string_literal: true

class Quickbooks::RefreshTokensJob < ApplicationJob
  queue_as :default

  def perform
    Quickbooks::RefreshTokens.execute
  end
end
