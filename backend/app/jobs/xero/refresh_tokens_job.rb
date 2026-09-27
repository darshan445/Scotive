# frozen_string_literal: true

class Xero::RefreshTokensJob < ApplicationJob
  queue_as :default

  def perform
    Xero::RefreshTokens.execute
  end
end
