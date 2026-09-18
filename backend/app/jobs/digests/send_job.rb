# frozen_string_literal: true

class Digests::SendJob < ApplicationJob
  queue_as :default

  def perform
    Digests::Send.execute
  end
end
