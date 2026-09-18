# frozen_string_literal: true

module Api
  module V1
    module Qbo
      class ImportsController < Api::V1::BaseController
        def create
          result = ::Quickbooks::ImportOpenInvoices.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
