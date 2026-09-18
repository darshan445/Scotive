# frozen_string_literal: true

class User < ApplicationRecord
  ROLES = %w[owner admin member].freeze

  belongs_to :organization

  devise :database_authenticatable, :registerable, :recoverable,
         :trackable, :validatable,
         :jwt_authenticatable, jwt_revocation_strategy: JwtDenylist

  validates :role, inclusion: { in: ROLES }

  def jwt_payload
    { "organization_id" => organization_id }
  end

  def full_name
    [ first_name, last_name ].compact_blank.join(" ").presence
  end
end
