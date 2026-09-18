# frozen_string_literal: true

require "cgi"

module Api
  module V1
    class ClientsController < Api::V1::BaseController
      def index
        result = ::Clients::Index.execute(organization: current_organization)
        render_result(result)
      end

      def show
        result = ::Clients::Show.execute(
          organization: current_organization,
          email: CGI.unescape(params[:email].to_s)
        )
        render_result(result, failure_status: :not_found)
      end
    end
  end
end
