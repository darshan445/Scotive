# frozen_string_literal: true

module Api
  module V1
    module Xero
      class ImportsController < Api::V1::BaseController
        def create
          result = ::Xero::ImportOpenInvoices.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
