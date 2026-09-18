# frozen_string_literal: true

module Api
  module V1
    module Qbo
      class ConnectionsController < Api::V1::BaseController
        def show
          result = ::Quickbooks::ConnectionStatus.execute(organization: current_organization)
          render_result(result)
        end

        def destroy
          result = ::Quickbooks::Disconnect.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
